from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RecommendationQuery:
    user_id: str
    context: Mapping[str, object]
    filters: Mapping[str, object]


@dataclass(frozen=True)
class RecommendationBatch:
    item_ids: tuple[str, ...]
    exhausted: bool


class RecommendationProvider(Protocol):
    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch: ...
