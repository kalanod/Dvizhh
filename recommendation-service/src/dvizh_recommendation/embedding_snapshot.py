import hashlib
import json
from collections.abc import Sequence
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, FiniteFloat, model_validator

from .retrieval import EmbeddingSpace


class ItemVector(BaseModel, extra="forbid", frozen=True):
    item_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: tuple[FiniteFloat, ...]


class UserVector(BaseModel, extra="forbid", frozen=True):
    user_id: UUID
    values: tuple[FiniteFloat, ...]


class EmbeddingSnapshot(BaseModel, extra="forbid", frozen=True):
    space: EmbeddingSpace
    generated_at: AwareDatetime
    items: tuple[ItemVector, ...]
    users: tuple[UserVector, ...]

    @model_validator(mode="after")
    def validate_space_and_ids(self) -> Self:
        if self.space.dimension != 384 or self.space.metric != "cosine":
            raise ValueError("The index requires 384-dimensional cosine embeddings")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("Embedding snapshot contains duplicate item IDs")
        if len({user.user_id for user in self.users}) != len(self.users):
            raise ValueError("Embedding snapshot contains duplicate user IDs")
        return self


def catalog_content_hash(title: str, description: str, topic_ids: Sequence[UUID]) -> str:
    payload = [title, description, sorted(map(str, topic_ids))]
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()
