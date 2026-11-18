import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from dvizh_logging import log_dependency
from redis.asyncio import Redis

from .recommendations import RecommendationBatch, RecommendationProvider, RecommendationQuery

BATCH_SIZE = 100
SESSION_TTL_SECONDS = 30 * 60


class SessionNotFound(Exception):
    pass


class SessionOwnerMismatch(Exception):
    pass


class SessionParametersMismatch(Exception):
    pass


class InvalidPageToken(Exception):
    pass


class InvalidRequest(ValueError):
    pass


class IncompleteRecommendations(Exception):
    pass


@dataclass(frozen=True)
class RecommendationPage:
    item_ids: tuple[str, ...]
    next_page_token: str | None


@dataclass(frozen=True)
class _Refill:
    generation: str
    item_ids: tuple[str, ...]


_READ_PAGE = """
local key = KEYS[1]
local user_id = ARGV[1]
local parameters = ARGV[2]
local page_token = ARGV[3]
local page_size = tonumber(ARGV[4])
local ttl_seconds = ARGV[5]
local new_generation = ARGV[6]
local new_page_token = ARGV[7]
local expected_generation = ARGV[8]

if redis.call('EXISTS', key) == 0 then
    if page_token ~= '' or expected_generation ~= '' then return {-1} end
    redis.call('HSET', key, 'user', user_id, 'parameters', parameters,
        'generation', new_generation, 'count', 0, 'exhausted', 0)
end
if expected_generation ~= '' and redis.call('HGET', key, 'generation') ~= expected_generation then
    return {-1}
end
if redis.call('HGET', key, 'user') ~= user_id then return {-2} end
if redis.call('HGET', key, 'parameters') ~= parameters then return {-3} end
local offset = 0
if page_token ~= '' then
    local position = redis.call('HGET', key, 'token:' .. page_token)
    if not position then return {-4} end
    offset = tonumber(position)
end
local count = tonumber(redis.call('HGET', key, 'count'))
local exhausted = redis.call('HGET', key, 'exhausted') == '1'
redis.call('EXPIRE', key, ttl_seconds)
if offset + page_size > count and not exhausted then
    local result = {0, redis.call('HGET', key, 'generation')}
    for i = 0, count - 1 do
        result[#result + 1] = redis.call('HGET', key, 'item:' .. i)
    end
    return result
end
local finish = math.min(offset + page_size, count)
local token = ''
if finish < count or not exhausted then
    token = redis.call('HGET', key, 'position:' .. finish)
    if not token then
        token = new_page_token
        redis.call('HSET', key, 'position:' .. finish, token, 'token:' .. token, finish)
    end
end
local result = {1, token}
for i = offset, finish - 1 do
    result[#result + 1] = redis.call('HGET', key, 'item:' .. i)
end
return result
"""

_APPEND = """
local key = KEYS[1]
local expected_generation = ARGV[1]
local expected_count = tonumber(ARGV[2])
local exhausted = ARGV[3]
local ttl_seconds = ARGV[4]

if redis.call('HGET', key, 'generation') ~= expected_generation then return -1 end
local count = tonumber(redis.call('HGET', key, 'count'))
if count ~= expected_count or redis.call('HGET', key, 'exhausted') == '1' then
    return 0
end
for i = 5, #ARGV do
    redis.call('HSET', key, 'item:' .. count, ARGV[i])
    count = count + 1
end
redis.call('HSET', key, 'count', count, 'exhausted', exhausted)
redis.call('EXPIRE', key, ttl_seconds)
return 1
"""

_REFRESH = """
local key = KEYS[1]
local user_id = ARGV[1]
local ttl_seconds = ARGV[2]

if redis.call('EXISTS', key) == 0 then return -1 end
if redis.call('HGET', key, 'user') ~= user_id then return -2 end
redis.call('EXPIRE', key, ttl_seconds)
return 1
"""


class SessionStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._read_page = redis.register_script(_READ_PAGE)
        self._append = redis.register_script(_APPEND)
        self._refresh = redis.register_script(_REFRESH)

    @staticmethod
    def key(session_id: str) -> str:
        return "recsys:session:" + hashlib.sha256(session_id.encode()).hexdigest()

    async def read_page(
        self,
        query: RecommendationQuery,
        session_id: str,
        page_token: str | None,
        page_size: int,
        generation: str | None = None,
    ) -> RecommendationPage | _Refill:
        try:
            parameters = json.dumps(
                {"context": query.context, "filters": query.filters},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise InvalidRequest("context and filters must contain valid JSON values") from exc
        fingerprint = hashlib.sha256(parameters.encode()).hexdigest()
        with log_dependency("redis", "read_page"):
            result = await self._read_page(
                keys=[self.key(session_id)],
                args=[
                    query.user_id,
                    fingerprint,
                    page_token or "",
                    page_size,
                    SESSION_TTL_SECONDS,
                    uuid4().hex,
                    uuid4().hex,
                    generation or "",
                ],
            )
        errors = {
            -1: SessionNotFound,
            -2: SessionOwnerMismatch,
            -3: SessionParametersMismatch,
            -4: InvalidPageToken,
        }
        if result[0] in errors:
            raise errors[result[0]]
        if result[0] == 0:
            return _Refill(result[1], tuple(result[2:]))
        return RecommendationPage(tuple(result[2:]), result[1] or None)

    async def append(self, session_id: str, state: _Refill, batch: RecommendationBatch) -> None:
        with log_dependency("redis", "append_page"):
            result = await self._append(
                keys=[self.key(session_id)],
                args=[
                    state.generation,
                    len(state.item_ids),
                    int(batch.exhausted),
                    SESSION_TTL_SECONDS,
                    *batch.item_ids,
                ],
            )
        if result == -1:
            raise SessionNotFound

    async def refresh(self, user_id: str, session_id: str) -> None:
        with log_dependency("redis", "refresh_session"):
            result = await self._refresh(
                keys=[self.key(session_id)], args=[user_id, SESSION_TTL_SECONDS]
            )
        if result == -1:
            raise SessionNotFound
        if result == -2:
            raise SessionOwnerMismatch


class Pagination:
    def __init__(
        self,
        store: SessionStore,
        provider: RecommendationProvider,
        filter_available_items: Callable[[Sequence[str]], Awaitable[tuple[str, ...]]],
        *,
        timeout_seconds: float = 5,
    ) -> None:
        self.store = store
        self.provider = provider
        self.filter_available_items = filter_available_items
        self.timeout_seconds = timeout_seconds

    async def get_page(
        self,
        query: RecommendationQuery,
        session_id: str,
        *,
        page_size: int,
        page_token: str | None = None,
    ) -> RecommendationPage:
        if not 1 <= page_size <= BATCH_SIZE:
            raise InvalidRequest("page_size must be between 1 and 100")
        if page_token is not None and len(page_token) != 32:
            raise InvalidPageToken
        async with asyncio.timeout(self.timeout_seconds):
            generation = None
            while True:
                result = await self.store.read_page(
                    query, session_id, page_token, page_size, generation
                )
                if isinstance(result, RecommendationPage):
                    return RecommendationPage(
                        await self.filter_available_items(result.item_ids), result.next_page_token
                    )
                generation = result.generation
                batch = await self.provider.recommend(
                    query, limit=BATCH_SIZE, exclude_ids=result.item_ids
                )
                ids = set(batch.item_ids)
                if (
                    len(batch.item_ids) > BATCH_SIZE
                    or len(ids) != len(batch.item_ids)
                    or ids.intersection(result.item_ids)
                    or any(not item_id for item_id in batch.item_ids)
                    or (not batch.item_ids and not batch.exhausted)
                ):
                    raise IncompleteRecommendations
                await self.store.append(session_id, result, batch)

    async def refresh(self, user_id: str, session_id: str) -> None:
        async with asyncio.timeout(self.timeout_seconds):
            await self.store.refresh(user_id, session_id)
