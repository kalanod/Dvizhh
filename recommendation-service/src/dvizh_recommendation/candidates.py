from collections.abc import Sequence
from uuid import UUID

import asyncpg
from dvizh_logging import log_dependency

from .catalog import AVAILABLE_ITEMS_QUERY
from .recommendations import RecommendationBatch, RecommendationQuery

CANDIDATES_QUERY = (
    AVAILABLE_ITEMS_QUERY
    + """
    AND NOT (e.id = ANY($2::uuid[]))
ORDER BY
    e.published_at DESC NULLS LAST,
    e.id DESC
LIMIT $1;
"""
)


async def get_candidates(
    pool: asyncpg.Pool,
    limit: int = 20,
    *,
    exclude_ids: Sequence[UUID] = (),
    timeout_seconds: float = 5,
) -> list[UUID]:
    if type(limit) is not int:
        raise TypeError("limit must be an integer")

    if limit <= 0:
        raise ValueError("limit must be positive")

    with log_dependency("postgres", "get_candidates"):
        async with pool.acquire(timeout=timeout_seconds) as connection:
            rows = await connection.fetch(
                CANDIDATES_QUERY,
                limit,
                list(exclude_ids),
                timeout=timeout_seconds,
            )

    return [row["id"] for row in rows]


class LatestRecommendations:
    def __init__(self, pool: asyncpg.Pool, timeout_seconds: float = 5) -> None:
        self.pool = pool
        self.timeout_seconds = timeout_seconds

    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch:
        if query.filters:
            raise NotImplementedError("Filters are not implemented")
        item_ids = await get_candidates(
            self.pool,
            limit=limit + 1,
            exclude_ids=[UUID(item_id) for item_id in exclude_ids],
            timeout_seconds=self.timeout_seconds,
        )
        return RecommendationBatch(
            item_ids=tuple(str(item_id) for item_id in item_ids[:limit]),
            exhausted=len(item_ids) <= limit,
        )
