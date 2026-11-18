from collections.abc import Sequence
from datetime import UTC, datetime
from math import isfinite
from uuid import UUID

import asyncpg

from .catalog import CatalogFilters, catalog_items
from .features import FEATURE_VERSION, catalog_feature_snapshot
from .recommendations import (
    BASELINE_VERSION,
    CandidateGenerator,
    Ranker,
    RecommendationBatch,
    RecommendationQuery,
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
        snapshots = [catalog_feature_snapshot(row, as_of, self.version) for row in rows]
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
