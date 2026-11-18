from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from .catalog import CatalogFilters, catalog_items
from .recommendations import (
    BASELINE_VERSION,
    FeatureSnapshot,
    RecommendationBatch,
    RecommendationQuery,
)

FEATURE_VERSION = "catalog-v1"


def _snapshot(row: asyncpg.Record, as_of: datetime, algorithm_version: str) -> FeatureSnapshot:
    publication = row["published_at"] or row["created_at"]
    return FeatureSnapshot(
        occurrence_id=row["occurrence_id"],
        feature_version=FEATURE_VERSION,
        features={
            "hours_until_start": (row["starts_at"] - as_of).total_seconds() / 3600,
            "hours_since_publication": (as_of - publication).total_seconds() / 3600,
            "participants_count": row["participants_count"],
            "price_type": row["price_type"],
            "format": row["format"],
            "join_policy": row["join_policy"],
        },
        calculated_at=as_of,
        algorithm_version=algorithm_version,
    )


class LatestRecommendations:
    def __init__(
        self,
        pool: asyncpg.Pool,
        timeout_seconds: float = 5,
    ) -> None:
        self.pool = pool
        self.timeout_seconds = timeout_seconds
        self.version = BASELINE_VERSION

    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch:
        filters = CatalogFilters.from_query(query)
        as_of = datetime.now(UTC)
        excluded = [UUID(item_id) for item_id in exclude_ids]
        rows = await catalog_items(
            self.pool,
            filters,
            as_of=as_of,
            user_id=query.viewer_id,
            exclude_ids=excluded,
            limit=limit + 1,
            timeout_seconds=self.timeout_seconds,
        )
        page = rows[:limit]
        return RecommendationBatch(
            item_ids=tuple(str(row["item_id"]) for row in page),
            exhausted=len(rows) <= limit,
            snapshots=tuple(_snapshot(row, as_of, self.version) for row in page),
        )
