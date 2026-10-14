from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from dvizh_backend.database.models.enums import MediaStatus


class MediaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    uploaded_by_user_id: UUID
    original_filename: str | None
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    status: MediaStatus
    created_at: datetime

    @computed_field
    @property
    def content_url(self) -> str:
        return f"/api/media/{self.id}/content"


class MediaSelectionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: UUID | None
