from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class PlaceCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False)


class EventTimezoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: PlaceCoordinates | None
    user_id: UUID | None
    device_timezone: StrictStr = Field(min_length=1, max_length=100)

    @field_validator("device_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone name") from None
        return value


class EventTimezoneResponse(BaseModel):
    timezone: str
    source: Literal["device"]
    city: str | None = None
