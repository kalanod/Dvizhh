"""Timezone selection rules for event creation; no HTTP or persistence details."""

import asyncio
from contextlib import suppress
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..dto.timezone import EventTimezoneRequest, EventTimezoneResponse, PlaceCoordinates
from .errors import UserInactiveError, UserNotFoundError
from .place_geocoding import ProfileCityGeocoder
from .user_service import UserService

_finder = None
_finder_lock = Lock()


def _coordinate_timezone(latitude: float, longitude: float) -> str | None:
    global _finder
    if _finder is None:
        with _finder_lock:
            if _finder is None:
                from timezonefinder import TimezoneFinder

                _finder = TimezoneFinder()
    lookup = getattr(_finder, "timezone_at_land", _finder.timezone_at)
    timezone = lookup(lat=latitude, lng=longitude)
    if timezone is not None:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return None
    return timezone


class CoordinateTimezoneResolver:
    async def resolve(self, place: PlaceCoordinates) -> str | None:
        try:
            return await asyncio.to_thread(
                _coordinate_timezone, place.latitude, place.longitude
            )
        except (ImportError, OSError, ValueError, RuntimeError):
            return None


class EventTimezoneService:
    def __init__(
        self, users: UserService, cities: ProfileCityGeocoder,
        coordinates: CoordinateTimezoneResolver | None = None,
    ) -> None:
        self.users = users
        self.cities = cities
        self.coordinates = coordinates or CoordinateTimezoneResolver()

    async def resolve(self, request: EventTimezoneRequest) -> EventTimezoneResponse:
        if request.place is not None:
            timezone = await self.coordinates.resolve(request.place)
            if timezone:
                return EventTimezoneResponse(timezone=timezone, source="place")
        profile = None
        if request.user_id is not None:
            with suppress(UserNotFoundError, UserInactiveError):
                profile = await self.users.get_profile(request.user_id)
        if profile is not None:
            if profile.latitude is not None and profile.longitude is not None:
                timezone = await self.coordinates.resolve(PlaceCoordinates(
                    latitude=float(profile.latitude), longitude=float(profile.longitude)
                ))
                if timezone:
                    return EventTimezoneResponse(
                        timezone=timezone, source="profile_coordinates", city=profile.city
                    )
            if profile.city:
                city = await self.cities.coordinates(profile.city)
                if city:
                    coordinates, locality = city
                    timezone = await self.coordinates.resolve(coordinates)
                    if timezone:
                        return EventTimezoneResponse(
                            timezone=timezone, source="profile_city", city=locality
                        )
        return EventTimezoneResponse(timezone=request.device_timezone, source="device")
