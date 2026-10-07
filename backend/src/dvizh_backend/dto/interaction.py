from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dvizh_backend.database.models.enums import InteractionType

ClientEventType = Literal[
    InteractionType.IMPRESSION,
    InteractionType.OPEN,
    InteractionType.JOIN_CLICK,
    InteractionType.EXTERNAL_LINK_CLICK,
]


class InteractionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: UUID
    item_id: UUID
    event_type: ClientEventType
    timestamp: AwareDatetime
    session_id: UUID | None = None
    request_id: UUID | None = None

    @model_validator(mode="after")
    def validate_origin(self) -> "InteractionDTO":
        if (self.session_id is None) != (self.request_id is None):
            raise ValueError("session_id and request_id must be provided together")
        return self


class InteractionBatchDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interactions: list[InteractionDTO] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_repeated_ids(self) -> "InteractionBatchDTO":
        seen: dict[UUID, InteractionDTO] = {}
        for interaction in self.interactions:
            previous = seen.get(interaction.interaction_id)
            if previous is not None and previous != interaction:
                raise ValueError("interaction_id cannot identify different interactions")
            seen[interaction.interaction_id] = interaction
        return self


class InteractionBatchResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_interaction_ids: list[UUID]
