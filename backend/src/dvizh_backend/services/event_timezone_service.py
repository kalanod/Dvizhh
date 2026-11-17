"""Compatibility for older clients: event time always comes from their browser."""

from dvizh_backend.api.schemas.timezone import EventTimezoneRequest, EventTimezoneResponse


class EventTimezoneService:
    async def resolve(self, request: EventTimezoneRequest) -> EventTimezoneResponse:
        return EventTimezoneResponse(timezone=request.device_timezone, source="device")
