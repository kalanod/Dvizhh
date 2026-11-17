"""Shared card projection for geographical discovery and other event read models."""

from uuid import UUID

from dvizh_backend.api.schemas.event import EventDTO, LocationDTO, UserSummaryDTO
from dvizh_backend.database.services.event_queries import EventQueryService, EventRow


class EventPresenter:
    def __init__(self, queries: EventQueryService):
        self.queries = queries

    async def to_dtos(
        self, rows: list[EventRow], *, viewer_id: UUID | None = None
    ) -> list[EventDTO]:
        if not rows:
            return []
        events = [row.event for row in rows]
        tags = await self.queries.event_tags(event.id for event in events)
        locations = await self.queries.locations(
            event.location_id for event in events if event.location_id is not None
        )
        organizers = await self.queries.profiles(
            event.organizer_user_id for event in events if event.organizer_user_id is not None
        )

        dtos = []
        covers = await self.queries.covers(event.id for event in events)
        personal_states = (
            await self.queries.personal_states(viewer_id, rows) if viewer_id is not None else {}
        )
        for row in rows:
            event, occurrence = row.event, row.occurrence
            location = locations.get(event.location_id)
            organizer = organizers.get(event.organizer_user_id)
            dtos.append(
                EventDTO(
                    id=event.id,
                    occurrence_id=occurrence.id,
                    slug=event.slug,
                    title=event.title,
                    description=event.description,
                    tags=tags.get(event.id, []),
                    starts_at=occurrence.starts_at,
                    ends_at=occurrence.ends_at,
                    timezone=occurrence.timezone,
                    is_all_day=occurrence.is_all_day,
                    format=event.format,
                    location=LocationDTO.model_validate(location) if location else None,
                    online_url=event.online_url,
                    registration_url=event.registration_url,
                    price_type=event.price_type,
                    price_min=event.price_min,
                    price_max=event.price_max,
                    currency=event.currency,
                    capacity=event.capacity,
                    participants_count=row.participants_count,
                    status=event.status,
                    visibility=event.visibility,
                    join_policy=event.join_policy,
                    organizer=UserSummaryDTO.model_validate(organizer) if organizer else None,
                    published_at=event.published_at,
                    created_at=event.created_at,
                    cover_media_id=covers.get(event.id),
                    cover_url=(
                        f"/api/media/{covers[event.id]}/content" if event.id in covers else None
                    ),
                    personal_state=personal_states.get(occurrence.id),
                )
            )
        return dtos
