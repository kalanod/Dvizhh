from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActorDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: UUID


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_id: UUID
    actor_id: UUID | None
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None
