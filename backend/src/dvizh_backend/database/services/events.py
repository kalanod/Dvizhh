from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update

from ..models import Event, EventOccurrence, EventParticipation, EventTopic
from ..models.enums import (
    EventPriceType,
    EventStatus,
    EventVisibility,
    OccurrenceStatus,
    ParticipationStatus,
)
from .access import can_manage_event
from .base import BaseCRUDService
from .exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
)


class EventService(BaseCRUDService[Event]):
    model = Event

    async def create_with_occurrence(
        self,
        event: Event,
        occurrence: EventOccurrence,
        *,
        topic_ids: Iterable[UUID] = (),
    ) -> Event:
        self.session.add(event)
        await self.session.flush()

        occurrence.event_id = event.id
        self.session.add(occurrence)
        self.session.add_all(EventTopic(event_id=event.id, topic_id=value) for value in topic_ids)
        await self.session.flush()
        return event

    async def publish(self, event_id: UUID, actor_user_id: UUID) -> Event:
        event = await self._get_locked(event_id)
        await self._require_manager(event, actor_user_id)
        if event.status != EventStatus.DRAFT:
            raise InvalidStateTransitionError("Only a draft event can be published")

        has_occurrence = await self.session.scalar(
            select(
                EventOccurrence.id
            ).where(EventOccurrence.event_id == event.id).limit(1)
        )
        if has_occurrence is None:
            raise InvalidStateTransitionError("An event needs at least one occurrence")

        event.status = EventStatus.PUBLISHED
        event.published_at = datetime.now(UTC)
        await self.session.flush()
        return event

    async def cancel(self, event_id: UUID, actor_user_id: UUID) -> Event:
        event = await self._get_locked(event_id)
        await self._require_manager(event, actor_user_id)
        if event.status not in {EventStatus.DRAFT, EventStatus.PUBLISHED}:
            raise InvalidStateTransitionError("This event cannot be cancelled")

        now = datetime.now(UTC)
        event.status = EventStatus.CANCELLED
        event.cancelled_at = now
        await self.session.execute(
            update(EventOccurrence)
            .where(
                EventOccurrence.event_id == event.id,
                EventOccurrence.status == OccurrenceStatus.SCHEDULED,
            )
            .values(status=OccurrenceStatus.CANCELLED, cancelled_at=now)
        )
        await self.session.flush()
        return event

    async def set_topics(
        self, event_id: UUID, actor_user_id: UUID, topic_ids: Iterable[UUID]
    ) -> None:
        event = await self._get_locked(event_id)
        await self._require_manager(event, actor_user_id)
        await self.session.execute(
            EventTopic.__table__.delete().where(EventTopic.event_id == event.id)
        )
        self.session.add_all(
            EventTopic(event_id=event.id, topic_id=topic_id) for topic_id in set(topic_ids)
        )
        await self.session.flush()

    async def list_upcoming(
        self,
        *,
        starts_from: datetime | None = None,
        starts_until: datetime | None = None,
        topic_ids: Sequence[UUID] = (),
        free_only: bool = False,
        available_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[tuple[Event, EventOccurrence]]:
        starts_from = starts_from or datetime.now(UTC)
        statement: Select[tuple[Event, EventOccurrence]] = (
            select(Event, EventOccurrence)
            .join(EventOccurrence, EventOccurrence.event_id == Event.id)
            .where(
                Event.status == EventStatus.PUBLISHED,
                Event.visibility == EventVisibility.PUBLIC,
                Event.deleted_at.is_(None),
                EventOccurrence.status == OccurrenceStatus.SCHEDULED,
                EventOccurrence.starts_at >= starts_from,
            )
        )

        if starts_until is not None:
            statement = statement.where(EventOccurrence.starts_at < starts_until)
        if topic_ids:
            statement = statement.join(EventTopic, EventTopic.event_id == Event.id).where(
                EventTopic.topic_id.in_(topic_ids)
            )
        if free_only:
            statement = statement.where(Event.price_type == EventPriceType.FREE)
        if available_only:
            going_count = (
                select(func.count(EventParticipation.id))
                .where(
                    EventParticipation.occurrence_id == EventOccurrence.id,
                    EventParticipation.status == ParticipationStatus.GOING,
                )
                .correlate(EventOccurrence)
                .scalar_subquery()
            )
            effective_capacity = func.coalesce(EventOccurrence.capacity_override, Event.capacity)
            statement = statement.where(
                or_(effective_capacity.is_(None), going_count < effective_capacity)
            )

        result = await self.session.execute(
            statement.distinct()
            .order_by(EventOccurrence.starts_at, Event.published_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.tuples().all()

    async def search_text(
        self,
        query: str,
        *,
        starts_from: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[tuple[Event, EventOccurrence, float]]:
        starts_from = starts_from or datetime.now(UTC)
        tsquery = func.websearch_to_tsquery("russian", query)
        rank = func.ts_rank_cd(Event.search_document, tsquery).label("rank")
        statement = (
            select(Event, EventOccurrence, rank)
            .join(EventOccurrence, EventOccurrence.event_id == Event.id)
            .where(
                Event.status == EventStatus.PUBLISHED,
                Event.visibility == EventVisibility.PUBLIC,
                Event.deleted_at.is_(None),
                EventOccurrence.status == OccurrenceStatus.SCHEDULED,
                EventOccurrence.starts_at >= starts_from,
                Event.search_document.op("@@")(tsquery),
            )
            .order_by(rank.desc(), EventOccurrence.starts_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return result.tuples().all()

    async def _get_locked(self, event_id: UUID) -> Event:
        event = await self.session.scalar(
            select(Event).where(Event.id == event_id).with_for_update()
        )
        if event is None:
            raise EntityNotFoundError("Event not found")
        return event

    async def _require_manager(self, event: Event, user_id: UUID) -> None:
        if not await can_manage_event(self.session, event, user_id):
            raise PermissionDeniedError("User cannot manage this event")
