from typing import Literal

from pydantic import BaseModel, Field


class MapClientError(BaseModel):
    stage: Literal["script_load", "sdk_missing", "sdk_ready", "map_init", "marker_update"]
    message: str | None = Field(default=None, max_length=2000)
    online: bool | None = None
