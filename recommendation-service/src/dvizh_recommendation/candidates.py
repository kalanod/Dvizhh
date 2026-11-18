from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from uuid import UUID

import asyncpg
from pydantic import JsonValue

from .catalog import CatalogFilters, catalog_items
from .features import (
    FEATURE_SCHEMAS,
    FEATURE_VERSION,
    HNSW_FEATURE_VERSION,
    catalog_feature_snapshot,
)
from .recommendations import (
    BASELINE_VERSION,
    CandidateGenerator,
    GeneratorUnavailable,
    Ranker,
    RecommendationBatch,
    RecommendationQuery,
)


class RetrievalScoreRanker:
    def __init__(self, source: str, feature_version: str = HNSW_FEATURE_VERSION) -> None:
        self.feature_version = feature_version
        self.feature_name = f"{source}_score"
        if self.feature_name not in FEATURE_SCHEMAS[feature_version]:
            raise ValueError(f"Missing retrieval feature: {self.feature_name}")
        self.version = f"{source}-score-v1"

    async def score(self, items: Sequence[Mapping[str, JsonValue]]) -> list[float | None]:
        scores = []
        for item in items:
            value = item[self.feature_name]
            if value is not None and not isinstance(value, (int, float)):
                raise ValueError(f"Invalid retrieval feature: {self.feature_name}")
            scores.append(value)
        return scores


class RecommendationPipeline:
    def __init__(
        self,
        pool: asyncpg.Pool,
        timeout_seconds: float = 5,
        *,
        ranker: Ranker | None = None,
        generators: Sequence[CandidateGenerator] = (),
        version: str | None = None,
        algorithm_version: str | None = None,
    ) -> None:
        if ranker is not None and ranker.feature_version not in FEATURE_SCHEMAS:
            raise ValueError("Ranker feature schema is incompatible")
        if generators and version is None:
            raise ValueError("A version is required when using candidate generators")
        self.pool = pool
        self.timeout_seconds = timeout_seconds
        self.ranker = ranker
        self.generators = tuple(generators)
        if len({generator.name for generator in self.generators}) != len(self.generators):
            raise ValueError("Candidate generator names must be unique")
        self.version = version or (ranker.version if ranker is not None else BASELINE_VERSION)
        self.algorithm_version = algorithm_version or self.version
        self.feature_version = ranker.feature_version if ranker is not None else FEATURE_VERSION

    async def _retrieve(
        self,
        query: RecommendationQuery,
        eligible: Mapping[UUID, asyncpg.Record],
        excluded: Sequence[UUID],
        limit: int,
    ) -> tuple[dict[UUID, dict[str, float]], bool]:
        eligible_ids = tuple(eligible)
        selected: dict[UUID, dict[str, float]] = {}
        exhausted = True
        available = False
        unavailable = None
        for generator in self.generators:
            try:
                result = await generator.generate(
                    query, limit=limit, exclude_ids=excluded, eligible_ids=eligible_ids
                )
            except GeneratorUnavailable as exc:
                unavailable = exc
                continue
            available = True
            exhausted = exhausted and result.exhausted
            for item in result.items:
                if item.item_id not in eligible:
                    continue
                scores = selected.setdefault(item.item_id, {})
                if item.score is not None:
                    if not isfinite(item.score):
                        raise ValueError(f"Non-finite candidate score from {generator.name}")
                    scores.setdefault(generator.name, item.score)
        if not available and unavailable is not None:
            raise unavailable
        return selected, exhausted

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
        source_scores: dict[UUID, dict[str, float]] = {}
        if self.generators and rows:
            eligible = {row["item_id"]: row for row in rows}
            source_scores, exhausted = await self._retrieve(query, eligible, excluded, limit + 1)
            rows = [eligible[item_id] for item_id in source_scores]
        snapshots = [
            catalog_feature_snapshot(
                row,
                as_of,
                self.algorithm_version,
                feature_version=self.feature_version,
                source_scores=source_scores.get(row["item_id"]),
            )
            for row in rows
        ]
        order = list(range(len(rows)))
        if self.ranker is not None and snapshots:
            scores = await self.ranker.score([snapshot.features for snapshot in snapshots])
            if len(scores) != len(rows) or any(s is not None and not isfinite(s) for s in scores):
                raise RuntimeError("Ranker returned invalid scores")
            order.sort(key=lambda i: (scores[i] is not None, scores[i] or 0.0), reverse=True)
        return RecommendationBatch(
            item_ids=tuple(str(rows[index]["item_id"]) for index in order[:limit]),
            exhausted=exhausted and len(rows) <= limit,
            snapshots=tuple(snapshots[index] for index in order[:limit]),
        )
