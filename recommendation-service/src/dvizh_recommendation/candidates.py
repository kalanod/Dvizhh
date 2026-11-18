from collections.abc import Sequence
from datetime import UTC, datetime
from math import isfinite
from uuid import UUID

import asyncpg

from .catalog import CatalogFilters, catalog_items
from .recommendations import (
    BASELINE_VERSION,
    CandidateGenerator,
    FeatureSnapshot,
    Ranker,
    RecommendationBatch,
    RecommendationQuery,
)

FEATURE_VERSION = "catalog-v1"
FEATURE_SCHEMA = {
    "hours_until_start": "number",
    "hours_since_publication": "number",
    "participants_count": "number",
    "price_type": "category",
    "format": "category",
    "join_policy": "category",
}


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
    rows = await catalog_items(
        pool,
        CatalogFilters(),
        as_of=datetime.now(UTC),
        exclude_ids=exclude_ids,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )
    return [row["item_id"] for row in rows]


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
        *,
        ranker: Ranker | None = None,
        generators: Sequence[CandidateGenerator] = (),
        version: str | None = None,
    ) -> None:
        if ranker is not None and ranker.feature_version != FEATURE_VERSION:
            raise ValueError("Ranker feature schema is incompatible")
        if generators and version is None:
            raise ValueError("A version is required when using candidate generators")
        self.pool = pool
        self.timeout_seconds = timeout_seconds
        self.ranker = ranker
        self.generators = tuple(generators)
        self.version = version or (ranker.version if ranker is not None else BASELINE_VERSION)

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
            limit=limit + 1 if not self.generators else None,
            timeout_seconds=self.timeout_seconds,
        )
        exhausted = True
        if self.generators and rows:
            eligible = {row["item_id"]: row for row in rows}
            eligible_ids = tuple(eligible)
            selected = {}
            for generator in self.generators:
                result = await generator.generate(
                    query, limit=limit + 1, exclude_ids=excluded, eligible_ids=eligible_ids
                )
                exhausted = exhausted and result.exhausted
                for item in result.items:
                    if item.item_id in eligible:
                        selected.setdefault(item.item_id, eligible[item.item_id])
            rows = list(selected.values())
        snapshots = [_snapshot(row, as_of, self.version) for row in rows]
        order = list(range(len(rows)))
        if self.ranker is not None and snapshots:
            scores = await self.ranker.score([snapshot.features for snapshot in snapshots])
            if len(scores) != len(rows) or not all(map(isfinite, scores)):
                raise RuntimeError("Ranker returned invalid scores")
            order.sort(key=lambda index: -scores[index])
        return RecommendationBatch(
            item_ids=tuple(str(rows[index]["item_id"]) for index in order[:limit]),
            exhausted=exhausted and len(rows) <= limit,
            snapshots=tuple(snapshots[index] for index in order[:limit]),
        )
