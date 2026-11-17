from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvizh_backend.api.schemas.event import EventDTO
from dvizh_backend.database.models.enums import InvitationStatus


class CreateInvitationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    invitee_id: UUID
    message: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_invitation(self) -> "CreateInvitationDTO":
        if self.actor_id == self.invitee_id:
            raise ValueError("Cannot invite yourself")
        return self


class InvitationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurrence_id: UUID
    inviter_user_id: UUID
    invitee_user_id: UUID
    invitee_name: str | None = None
    status: InvitationStatus
    message: str | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvitationCardDTO(BaseModel):
    invitation: InvitationDTO
    event: EventDTO


class InvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    accept: bool
