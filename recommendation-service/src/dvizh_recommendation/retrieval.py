from typing import Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    FiniteFloat,
    JsonValue,
    model_validator,
)

type DistanceMetric = Literal["cosine", "inner_product", "l2"]


class EmbeddingSpace(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    model_id: str = Field(min_length=1, pattern=r"\S")
    dimension: int = Field(gt=0, strict=True)
    metric: DistanceMetric


class Embedding(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    space: EmbeddingSpace
    values: tuple[FiniteFloat, ...]

    @model_validator(mode="after")
    def validate_vector(self) -> Self:
        if len(self.values) != self.space.dimension:
            raise ValueError("Vector dimension does not match embedding space")
        if self.space.metric == "cosine" and not any(self.values):
            raise ValueError("Cosine search requires a nonzero vector")
        return self


class IndexedItem(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    item_id: UUID
    embedding: Embedding
    content_hash: str = Field(min_length=1)
    is_candidate: bool = Field(strict=True)
    source_updated_at: AwareDatetime
    last_ends_at: AwareDatetime | None = None
    next_starts_at: AwareDatetime | None = None
    price_type: str | None = None
    format: str | None = None
    city: str | None = None
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    topic_ids: tuple[UUID, ...] = ()


class ItemSearchQuery(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    embedding: Embedding
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    limit: int = Field(gt=0, strict=True)


class ScoredItem(BaseModel, extra="forbid", frozen=True, allow_inf_nan=False):
    item_id: UUID
    retrieval_score: FiniteFloat
