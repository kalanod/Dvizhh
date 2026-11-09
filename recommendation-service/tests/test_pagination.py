import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from dvizh_recommendation.pagination import (
    IncompleteRecommendations,
    InvalidPageToken,
    Pagination,
    SessionNotFound,
    SessionOwnerMismatch,
    SessionParametersMismatch,
    SessionStore,
)
from dvizh_recommendation.recommendations import RecommendationBatch, RecommendationQuery

pytestmark = pytest.mark.integration


async def keep_items(item_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(item_ids)


class OrderedRecommendations:
    def __init__(self, count: int) -> None:
        self.item_ids = tuple(str(uuid4()) for _ in range(count))
        self.calls: list[tuple[int, tuple[str, ...]]] = []

    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch:
        self.calls.append((limit, tuple(exclude_ids)))
        excluded = set(exclude_ids)
        remaining = tuple(item_id for item_id in self.item_ids if item_id not in excluded)
        return RecommendationBatch(remaining[:limit], len(remaining) <= limit)


@asynccontextmanager
async def redis_sessions(url: str, *session_ids: str) -> AsyncIterator[Redis]:
    async with Redis.from_url(url, decode_responses=True) as redis:
        try:
            yield redis
        finally:
            await redis.delete(*(SessionStore.key(session_id) for session_id in session_ids))


def test_pages_cross_batches_without_reordering_or_recalculating_retries(
    integration_redis_url: str,
) -> None:
    async def run() -> None:
        session_id = uuid4().hex
        query = RecommendationQuery("user", {}, {})
        provider = OrderedRecommendations(225)
        async with redis_sessions(integration_redis_url, session_id) as redis:
            pagination = Pagination(SessionStore(redis), provider, keep_items)
            first = await pagination.get_page(query, session_id, page_size=30)
            assert await pagination.get_page(query, session_id, page_size=30) == first
            assert len(provider.calls) == 1

            collected = list(first.item_ids)
            page = first
            while page.next_page_token is not None:
                token = page.next_page_token
                page = await pagination.get_page(query, session_id, page_size=30, page_token=token)
                calls = len(provider.calls)
                assert (
                    await pagination.get_page(query, session_id, page_size=30, page_token=token)
                    == page
                )
                assert len(provider.calls) == calls
                collected.extend(page.item_ids)

            assert tuple(collected) == provider.item_ids
            assert len(page.item_ids) == 15
            assert provider.calls == [
                (100, ()),
                (100, provider.item_ids[:100]),
                (100, provider.item_ids[:200]),
            ]
            provider.item_ids += (str(uuid4()),)
            assert (
                await pagination.get_page(query, session_id, page_size=30, page_token=token) == page
            )
            assert len(provider.calls) == 3

    asyncio.run(run())


@pytest.mark.parametrize("refill", [False, True], ids=["initialization", "refill"])
def test_concurrent_service_instances_commit_one_order(
    integration_redis_url: str, refill: bool
) -> None:
    async def run() -> None:
        session_id = uuid4().hex
        query = RecommendationQuery("user", {}, {})
        barrier = asyncio.Barrier(2)

        class ConcurrentRecommendations(OrderedRecommendations):
            wait_for_peer = False

            async def recommend(self, query, *, limit, exclude_ids):
                result = await super().recommend(query, limit=limit, exclude_ids=exclude_ids)
                if self.wait_for_peer:
                    await barrier.wait()
                return result

        provider = ConcurrentRecommendations(225)
        async with (
            redis_sessions(integration_redis_url, session_id) as redis,
            Redis.from_url(integration_redis_url, decode_responses=True) as peer_redis,
        ):
            first_instance = Pagination(SessionStore(redis), provider, keep_items)
            second_instance = Pagination(SessionStore(peer_redis), provider, keep_items)
            collected = []
            token = None
            if refill:
                first = await first_instance.get_page(query, session_id, page_size=100)
                collected.extend(first.item_ids)
                token = first.next_page_token

            provider.wait_for_peer = True
            first, second = await asyncio.gather(
                first_instance.get_page(query, session_id, page_size=100, page_token=token),
                second_instance.get_page(query, session_id, page_size=100, page_token=token),
            )
            provider.wait_for_peer = False
            assert first == second
            collected.extend(first.item_ids)
            page = first
            while page.next_page_token is not None:
                page = await second_instance.get_page(
                    query, session_id, page_size=100, page_token=page.next_page_token
                )
                collected.extend(page.item_ids)
            assert tuple(collected) == provider.item_ids

    asyncio.run(run())


def test_session_owner_parameters_and_tokens_cannot_be_changed(
    integration_redis_url: str,
) -> None:
    async def run() -> None:
        session_id, other_session = uuid4().hex, uuid4().hex
        query = RecommendationQuery("user", {"city": "Moscow"}, {"free_only": True})
        provider = OrderedRecommendations(120)
        async with redis_sessions(integration_redis_url, session_id, other_session) as redis:
            pagination = Pagination(SessionStore(redis), provider, keep_items)
            first = await pagination.get_page(query, session_id, page_size=20)
            await pagination.get_page(query, other_session, page_size=20)
            cases = [
                (
                    RecommendationQuery("another-user", query.context, query.filters),
                    session_id,
                    first.next_page_token,
                    SessionOwnerMismatch,
                ),
                (
                    RecommendationQuery(query.user_id, {"city": "Kazan"}, query.filters),
                    session_id,
                    first.next_page_token,
                    SessionParametersMismatch,
                ),
                (
                    RecommendationQuery(query.user_id, query.context, {"free_only": False}),
                    session_id,
                    first.next_page_token,
                    SessionParametersMismatch,
                ),
                (query, other_session, first.next_page_token, InvalidPageToken),
                (query, session_id, uuid4().hex, InvalidPageToken),
                (query, session_id, "invalid", InvalidPageToken),
            ]
            for request_query, target_session, token, expected_error in cases:
                with pytest.raises(expected_error):
                    await pagination.get_page(
                        request_query, target_session, page_size=20, page_token=token
                    )
            with pytest.raises(SessionOwnerMismatch):
                await pagination.refresh("another-user", session_id)
            assert await pagination.get_page(query, session_id, page_size=20) == first
            assert len(provider.calls) == 2

    asyncio.run(run())


def test_reads_and_heartbeat_renew_ttl_but_late_refills_cannot_restore_expired_sessions(
    integration_redis_url: str,
) -> None:
    async def run() -> None:
        session_id = uuid4().hex
        query = RecommendationQuery("user", {}, {})
        entered, release = asyncio.Event(), asyncio.Event()

        class SlowRecommendations(OrderedRecommendations):
            async def recommend(self, query, *, limit, exclude_ids):
                if exclude_ids:
                    entered.set()
                    await release.wait()
                return await super().recommend(query, limit=limit, exclude_ids=exclude_ids)

        provider = SlowRecommendations(120)
        async with redis_sessions(integration_redis_url, session_id) as redis:
            pagination = Pagination(SessionStore(redis), provider, keep_items)
            key = SessionStore.key(session_id)
            first = await pagination.get_page(query, session_id, page_size=100)
            await redis.expire(key, 10)
            await pagination.get_page(query, session_id, page_size=20)
            assert await redis.ttl(key) > 29 * 60
            await redis.expire(key, 10)
            await pagination.refresh(query.user_id, session_id)
            assert await redis.ttl(key) > 29 * 60

            task = asyncio.create_task(
                pagination.get_page(
                    query, session_id, page_size=20, page_token=first.next_page_token
                )
            )
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                await redis.expire(key, 0)
            finally:
                release.set()
            with pytest.raises(SessionNotFound):
                await task
            with pytest.raises(SessionNotFound):
                await pagination.refresh(query.user_id, session_id)
            with pytest.raises(SessionNotFound):
                await pagination.get_page(
                    query, session_id, page_size=20, page_token=first.next_page_token
                )
            assert not await redis.exists(key)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["timeout", "incomplete"])
def test_short_nonterminal_batches_and_refill_failures_preserve_progress(
    integration_redis_url: str, failure: str
) -> None:
    async def run() -> None:
        session_id = uuid4().hex
        query = RecommendationQuery("user", {}, {})
        item_ids = tuple(str(uuid4()) for _ in range(27))

        class PartialRecommendations:
            calls = 0

            async def recommend(self, query, *, limit, exclude_ids):
                self.calls += 1
                if self.calls == 1:
                    return RecommendationBatch(item_ids[:7], exhausted=False)
                assert tuple(exclude_ids) == item_ids[:7]
                if self.calls == 2:
                    if failure == "timeout":
                        raise TimeoutError
                    return RecommendationBatch((), exhausted=False)
                return RecommendationBatch(item_ids[7:], exhausted=True)

        async with redis_sessions(integration_redis_url, session_id) as redis:
            provider = PartialRecommendations()
            pagination = Pagination(SessionStore(redis), provider, keep_items)
            expected_error = TimeoutError if failure == "timeout" else IncompleteRecommendations
            with pytest.raises(expected_error):
                await pagination.get_page(query, session_id, page_size=20)
            first = await pagination.get_page(query, session_id, page_size=20)
            assert first.item_ids == item_ids[:20]
            assert first.next_page_token is not None
            last = await pagination.get_page(
                query, session_id, page_size=20, page_token=first.next_page_token
            )
            assert last.item_ids == item_ids[20:]
            assert last.next_page_token is None
            assert provider.calls == 3

    asyncio.run(run())


def test_calculation_deadline_does_not_break_cached_pages(integration_redis_url: str) -> None:
    async def run() -> None:
        session_id = uuid4().hex
        query = RecommendationQuery("user", {}, {})
        release = asyncio.Event()

        class BlockingRecommendations(OrderedRecommendations):
            async def recommend(self, query, *, limit, exclude_ids):
                if exclude_ids:
                    await release.wait()
                return await super().recommend(query, limit=limit, exclude_ids=exclude_ids)

        provider = BlockingRecommendations(120)
        async with redis_sessions(integration_redis_url, session_id) as redis:
            pagination = Pagination(SessionStore(redis), provider, keep_items, timeout_seconds=0.1)
            first = await pagination.get_page(query, session_id, page_size=100)
            async with asyncio.timeout(2) as watchdog:
                with pytest.raises(TimeoutError):
                    await pagination.get_page(
                        query, session_id, page_size=20, page_token=first.next_page_token
                    )
            assert not watchdog.expired()
            assert await pagination.get_page(query, session_id, page_size=100) == first
            release.set()
            last = await pagination.get_page(
                query, session_id, page_size=20, page_token=first.next_page_token
            )
            assert last.item_ids == provider.item_ids[100:]
            assert last.next_page_token is None

    asyncio.run(run())
