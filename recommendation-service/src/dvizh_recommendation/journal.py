import hashlib
import json
from collections.abc import Sequence
from contextlib import suppress
from uuid import UUID

import asyncpg

from .recommendations import FeatureSnapshot, InvalidRequest, RecommendationQuery


class PageChanged(Exception):
    pass


class RecommendationJournal:
    def __init__(self, pool: asyncpg.Pool, *, timeout_seconds: float = 5) -> None:
        self.pool = pool
        self.timeout_seconds = timeout_seconds

    async def record(
        self,
        query: RecommendationQuery,
        session_id: str,
        request_id: str,
        item_ids: Sequence[str],
        snapshots: Sequence[FeatureSnapshot | None],
        *,
        page_size: int,
        page_token: str | None,
    ) -> None:
        with suppress(ValueError):
            request_id = str(UUID(request_id))
        parameters = json.dumps(
            [query.context, query.filters, page_size, page_token],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        parameters_hash = hashlib.sha256(parameters.encode()).hexdigest()
        snapshots = snapshots or (None,) * len(item_ids)
        items = json.dumps(
            [
                {"item_id": item_id} | (snapshot.model_dump(mode="json") if snapshot else {})
                for item_id, snapshot in zip(item_ids, snapshots, strict=True)
            ],
            separators=(",", ":"),
            allow_nan=False,
        )
        arguments = (request_id, session_id, query.user_id, parameters_hash, items)
        async with self.pool.acquire(timeout=self.timeout_seconds) as connection:
            inserted = await connection.fetchval(
                """
                INSERT INTO public.recommendation_pages (
                    request_id, session_id, user_id, parameters_hash, items
                ) VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (request_id) DO NOTHING
                RETURNING TRUE
                """,
                *arguments,
                timeout=self.timeout_seconds,
            )
            if inserted:
                return

            recorded = await connection.fetchrow(
                """
                SELECT session_id = $2 AND user_id = $3 AND parameters_hash = $4
                    AS same_request, items = $5::jsonb AS same_items
                FROM public.recommendation_pages
                WHERE request_id = $1
                """,
                *arguments,
                timeout=self.timeout_seconds,
            )
            if recorded is None or not recorded["same_request"]:
                raise InvalidRequest("request_id was already used for a different page")
            if not recorded["same_items"]:
                raise PageChanged
