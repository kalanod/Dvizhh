from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dvizh_backend.database.models.enums import FriendshipStatus, ProfileStatus


class UserDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    @field_validator("display_name", "city", check_fields=False)
    @classmethod
    def reject_blank_or_padded_text(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("text must be non-blank and have no surrounding whitespace")
        return value


class CreateProfileDTO(UserDTO):
    id: UUID = Field(description="User ID issued by the auth service")
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_media_id: UUID | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> "CreateProfileDTO":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class UpdateProfileDTO(UserDTO):
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$")
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_media_id: UUID | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)

    @model_validator(mode="after")
    def validate_patch(self) -> "UpdateProfileDTO":
        fields = self.model_fields_set
        if not fields:
            raise ValueError("at least one field is required")
        if "username" in fields and self.username is None:
            raise ValueError("username cannot be null")
        if "display_name" in fields and self.display_name is None:
            raise ValueError("display_name cannot be null")
        if ("latitude" in fields) != ("longitude" in fields):
            raise ValueError("latitude and longitude must be updated together")
        if "latitude" in fields and (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be set or both be null")
        return self


class ProfileDTO(UserDTO):
    id: UUID
    username: str
    display_name: str
    bio: str | None
    avatar_media_id: UUID | None
    city: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    status: ProfileStatus
    created_at: datetime
    updated_at: datetime


class FriendshipDTO(UserDTO):
    user_low_id: UUID
    user_high_id: UUID
    requested_by_user_id: UUID
    status: FriendshipStatus
    requested_at: datetime
    responded_at: datetime | None
    removed_at: datetime | None
