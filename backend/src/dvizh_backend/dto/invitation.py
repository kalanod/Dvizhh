from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dvizh_backend.database.models.enums import InvitationStatus

from .event import EventDTO


class CreateInvitationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    invitee_id: UUID
    message: str | None = Field(None, max_length=500)
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_invitation(self) -> "CreateInvitationDTO":
        if self.actor_id == self.invitee_id:
            raise ValueError("Cannot invite yourself")
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            raise ValueError("expires_at must be in the future")
        return self


class InvitationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurrence_id: UUID
    inviter_user_id: UUID
    invitee_user_id: UUID
    status: InvitationStatus
    message: str | None
    expires_at: datetime | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvitationCardDTO(BaseModel):
    invitation: InvitationDTO
    event: EventDTO
