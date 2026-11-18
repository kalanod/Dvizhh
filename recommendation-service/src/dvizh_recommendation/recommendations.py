from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, JsonValue

BASELINE_VERSION = "novelty-v1"


class InvalidRequest(ValueError):
    pass


class FeatureSnapshot(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    occurrence_id: UUID
    feature_version: str
    features: dict[str, JsonValue]
    calculated_at: AwareDatetime
    algorithm_version: str


@dataclass(frozen=True)
class RecommendationQuery:
    user_id: str
    context: Mapping[str, object]
    filters: Mapping[str, object]

    @property
    def viewer_id(self) -> UUID | None:
        try:
            return UUID(self.user_id)
        except ValueError:
            return None


@dataclass(frozen=True)
class RecommendationBatch:
    item_ids: tuple[str, ...]
    exhausted: bool
    snapshots: tuple[FeatureSnapshot | None, ...] = ()


class RecommendationProvider(Protocol):
    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch: ...


class Ranker(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def feature_version(self) -> str: ...

    async def score(self, items: Sequence[Mapping[str, JsonValue]]) -> Sequence[float]: ...
