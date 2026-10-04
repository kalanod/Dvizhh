import re
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.models import Event, EventOccurrence, Profile
from dvizh_backend.database.models.enums import EventOrigin, EventStatus, ProfileStatus
from dvizh_backend.database.services.catalog import LocationService, ProfileService
from dvizh_backend.database.services.event_queries import EventQueryService, EventRow
from dvizh_backend.database.services.events import EventService as EventCRUDService
from dvizh_backend.database.services.exceptions import EntityNotFoundError
from dvizh_backend.database.services.participation import ParticipationService
from dvizh_backend.dto.event import (
    CreateEventDTO,
    EventDTO,
    LocationDTO,
    ParticipantDTO,
    UpdateEventDTO,
    UserSummaryDTO,
)

from .errors import UserInactiveError, UserNotFoundError


class EventService:
    """Event and participation rules within one request-scoped database transaction.

    The API works with one occurrence per event: an event is created together with its
    occurrence, and participation is addressed through the earliest occurrence.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.events = EventCRUDService(session)
        self.queries = EventQueryService(session)
        self.participations = ParticipationService(session)
        self.profiles = ProfileService(session)
        self.locations = LocationService(session)

    async def list_public(
        self,
        *,
        text_query: str | None = None,
        tag: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        free_only: bool = False,
        available_only: bool = False,
        friends_of: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[EventDTO]:
        rows = await self.queries.list_public(
            text_query=text_query.strip() if text_query and text_query.strip() else None,
            tag=tag.strip().lower() if tag and tag.strip() else None,
            date_from=date_from,
            date_to=date_to,
            free_only=free_only,
            available_only=available_only,
            friends_of=friends_of,
            offset=offset,
            limit=limit,
        )
        return await self._to_dtos(rows)

    async def list_calendar(self, user_id: UUID) -> list[EventDTO]:
        await self._require_active_profile(user_id)
        return await self._to_dtos(await self.queries.list_going(user_id))

    async def get_event(self, event_id: UUID) -> EventDTO:
        row = await self._require_row(event_id)
        return (await self._to_dtos([row]))[0]

    async def create_event(self, data: CreateEventDTO) -> EventDTO:
        await self._require_active_profile(data.organizer_id)
        location_id = await self._save_location(None, data.location)
        event = Event(
            slug=self._make_slug(data.title),
            origin=EventOrigin.USER,
            status=EventStatus.PUBLISHED,
            published_at=datetime.now(UTC),
            organizer_user_id=data.organizer_id,
            created_by_user_id=data.organizer_id,
            location_id=location_id,
            **data.event_columns(),
        )
        occurrence = EventOccurrence(**data.occurrence_columns())
        topic_ids = await self.queries.ensure_topics(data.tags)
        await self.events.create_with_occurrence(event, occurrence, topic_ids=topic_ids)
        return await self.get_event(event.id)

    async def update_event(self, event_id: UUID, data: UpdateEventDTO) -> EventDTO:
        row = await self._require_row(event_id)
        previous_location_id = row.event.location_id
        location_id = await self._save_location(previous_location_id, data.location)
        for column, value in data.occurrence_columns().items():
            setattr(row.occurrence, column, value)
        await self.events.update(row.event, location_id=location_id, **data.event_columns())
        if location_id is None and previous_location_id is not None:
            await self._delete_location(previous_location_id)
        await self.queries.replace_topics(event_id, await self.queries.ensure_topics(data.tags))
        return await self.get_event(event_id)

    async def delete_event(self, event_id: UUID) -> None:
        row = await self._require_row(event_id)
        await self.events.update(row.event, deleted_at=datetime.now(UTC))

    async def list_participants(self, event_id: UUID) -> list[ParticipantDTO]:
        row = await self._require_row(event_id)
        participants = await self.queries.list_participants(row.occurrence.id)
        return [
            ParticipantDTO(user=UserSummaryDTO.model_validate(profile), status=participation.status)
            for participation, profile in participants
        ]

    async def join(self, event_id: UUID, user_id: UUID) -> ParticipantDTO:
        row = await self._require_row(event_id)
        profile = await self._require_active_profile(user_id)
        participation = await self.participations.join(row.occurrence.id, user_id)
        return ParticipantDTO(
            user=UserSummaryDTO.model_validate(profile), status=participation.status
        )

    async def review_participation(
        self,
        event_id: UUID,
        user_id: UUID,
        actor_user_id: UUID,
        *,
        accept: bool,
        reason: str | None = None,
    ) -> ParticipantDTO:
        row = await self._require_row(event_id)
        participation = await self.queries.get_participation(row.occurrence.id, user_id)
        if participation is None:
            raise EntityNotFoundError("Participation not found")
        profile = await self._require_profile(user_id)
        participation = await self.participations.decide_request(
            participation.id, actor_user_id, approve=accept, reason=reason
        )
        return ParticipantDTO(
            user=UserSummaryDTO.model_validate(profile), status=participation.status
        )

    async def leave(self, event_id: UUID, user_id: UUID) -> None:
        row = await self._require_row(event_id)
        await self.participations.cancel(row.occurrence.id, user_id)

    async def _require_row(self, event_id: UUID) -> EventRow:
        row = await self.queries.get_primary(event_id)
        if row is None:
            raise EntityNotFoundError("Event not found")
        return row

    async def _require_profile(self, user_id: UUID) -> Profile:
        profile = await self.profiles.get_by_id(user_id)
        if profile is None:
            raise UserNotFoundError("Profile not found")
        return profile

    async def _require_active_profile(self, user_id: UUID) -> Profile:
        profile = await self._require_profile(user_id)
        if profile.status != ProfileStatus.ACTIVE:
            raise UserInactiveError("Profile is not active")
        return profile

    async def _save_location(
        self, location_id: UUID | None, data: LocationDTO | None
    ) -> UUID | None:
        """Create or update the event's own location row; returns its ID, if any."""
        if data is None:
            return None
        location = await self.locations.get_by_id(location_id) if location_id else None
        if location is None:
            return (await self.locations.create(**data.model_dump())).id
        await self.locations.update(location, **data.model_dump())
        return location.id

    async def _delete_location(self, location_id: UUID) -> None:
        location = await self.locations.get_by_id(location_id)
        if location is not None:
            await self.locations.delete(location)

    async def _to_dtos(self, rows: list[EventRow]) -> list[EventDTO]:
        if not rows:
            return []
        events = [row.event for row in rows]
        tags = await self.queries.topic_slugs(event.id for event in events)
        locations = await self.queries.locations(
            event.location_id for event in events if event.location_id is not None
        )
        organizers = await self.queries.profiles(
            event.organizer_user_id for event in events if event.organizer_user_id is not None
        )

        dtos = []
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
                )
            )
        return dtos

    @staticmethod
    def _make_slug(title: str) -> str:
        base = re.sub(r"[^\w]+", "-", title.lower()).strip("-")[:120]
        return f"{base}-{uuid4().hex[:8]}" if base else uuid4().hex
