"""One read contract for the geographical map and feed."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .event import EventDTO


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MapPoint(DiscoveryModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class MapBounds(DiscoveryModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def valid_area(self):
        if self.south > self.north:
            raise ValueError("Invalid latitude bounds")
        return self


class MapViewport(MapBounds):
    zoom: float = Field(ge=0, le=24)
    center: MapPoint

    @model_validator(mode="after")
    def positive_viewport(self):
        if (
            self.south == self.north
            or self.west == self.east
            or (self.west == 180 and self.east == -180)
        ):
            raise ValueError("Map viewport must have a positive area")
        return self


class DiscoveryFilters(DiscoveryModel):
    q: str = Field(default="", max_length=500)
    tag_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    free_only: bool = False
    available_only: bool = False
    friends_of: UUID | None = None
    viewer_id: UUID | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Invalid date range")
        return self


class DiscoveryRequest(DiscoveryModel):
    filters: DiscoveryFilters = Field(default_factory=DiscoveryFilters)
    viewport: MapViewport | None = None
    sort: Literal["distance", "newest", "start"] = "distance"
    selection_token: str | None = Field(default=None, max_length=12000)
    cursor: str | None = Field(default=None, max_length=16000)
    limit: int = Field(default=20, ge=1, le=50)
    include_map: bool = True


class MapItem(DiscoveryModel):
    id: str
    type: Literal["event", "cluster"]
    longitude: float
    latitude: float
    count: int = Field(ge=1)
    event_id: UUID | None = None
    selection_token: str | None = None
    bounds: MapBounds


class DiscoveryMap(DiscoveryModel):
    items: list[MapItem] = Field(max_length=30)
    total_events: int = Field(ge=0)


class DiscoveryFeed(DiscoveryModel):
    items: list[EventDTO]
    total_events: int = Field(ge=0)
    next_cursor: str | None = None


class DiscoveryResponse(DiscoveryModel):
    as_of: datetime
    map: DiscoveryMap | None = None
    feed: DiscoveryFeed
