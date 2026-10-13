from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Date, Select, case, cast, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Event,
    EventOccurrence,
    EventParticipation,
    EventTopic,
    Friendship,
    Location,
    Profile,
    Topic,
)
from ..models.enums import (
    EventPriceType,
    EventStatus,
    EventVisibility,
    FriendshipStatus,
    OccurrenceStatus,
    ParticipationStatus,
)

# Количество участников проведения со статусом «иду».
going_count = (
    select(func.count(EventParticipation.id))
    .where(
        EventParticipation.occurrence_id == EventOccurrence.id,
        EventParticipation.status == ParticipationStatus.GOING,
    )
    .correlate(EventOccurrence)
    .scalar_subquery()
)


@dataclass(frozen=True)
class EventRow:
    event: Event
    occurrence: EventOccurrence
    participants_count: int


class EventQueryService:
    """Read models for the event API: feed, calendar, participants and event details."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_primary(self, event_id: UUID) -> EventRow | None:
        """Event with its earliest occurrence; the API addresses participation through it."""
        statement = (
            self._select_rows()
            .where(Event.id == event_id)
            .order_by(EventOccurrence.starts_at)
            .limit(1)
        )
        rows = await self._fetch(statement)
        return rows[0] if rows else None

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
    ) -> list[EventRow]:
        statement = self._select_rows().where(
            Event.status == EventStatus.PUBLISHED,
            Event.visibility == EventVisibility.PUBLIC,
            EventOccurrence.status == OccurrenceStatus.SCHEDULED,
        )

        if text_query:
            tsquery = func.websearch_to_tsquery("russian", text_query)
            statement = statement.where(Event.search_document.op("@@")(tsquery))
        if tag:
            statement = statement.where(
                exists().where(
                    EventTopic.event_id == Event.id,
                    EventTopic.topic_id == Topic.id,
                    Topic.slug == tag,
                )
            )
        if date_from is not None:
            last_day = self._local_date(
                func.coalesce(EventOccurrence.ends_at, EventOccurrence.starts_at)
            )
            statement = statement.where(last_day >= date_from)
        if date_to is not None:
            statement = statement.where(self._local_date(EventOccurrence.starts_at) <= date_to)
        if free_only:
            statement = statement.where(Event.price_type == EventPriceType.FREE)
        if available_only:
            capacity = func.coalesce(EventOccurrence.capacity_override, Event.capacity)
            statement = statement.where(or_(capacity.is_(None), going_count < capacity))

        if friends_of is not None:
            friend_ids = select(
                case(
                    (Friendship.user_low_id == friends_of, Friendship.user_high_id),
                    else_=Friendship.user_low_id,
                )
            ).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.user_low_id == friends_of, Friendship.user_high_id == friends_of),
            )
            friends_going = (
                select(func.count(EventParticipation.id))
                .where(
                    EventParticipation.occurrence_id == EventOccurrence.id,
                    EventParticipation.status == ParticipationStatus.GOING,
                    EventParticipation.user_id.in_(friend_ids),
                )
                .correlate(EventOccurrence)
                .scalar_subquery()
            )
            statement = statement.order_by(friends_going.desc())

        statement = (
            statement.order_by(Event.published_at.desc(), EventOccurrence.starts_at)
            .offset(offset)
            .limit(limit)
        )
        return await self._fetch(statement)

    async def list_going(self, user_id: UUID) -> list[EventRow]:
        is_going = exists().where(
            EventParticipation.occurrence_id == EventOccurrence.id,
            EventParticipation.user_id == user_id,
            EventParticipation.status == ParticipationStatus.GOING,
        )
        return await self._fetch(
            self._select_rows().where(is_going).order_by(EventOccurrence.starts_at)
        )

    async def list_participants(
        self, occurrence_id: UUID
    ) -> Sequence[tuple[EventParticipation, Profile]]:
        result = await self.session.execute(
            select(EventParticipation, Profile)
            .join(Profile, Profile.id == EventParticipation.user_id)
            .where(
                EventParticipation.occurrence_id == occurrence_id,
                EventParticipation.status.in_(
                    [ParticipationStatus.GOING, ParticipationStatus.REQUESTED]
                ),
            )
            .order_by(EventParticipation.created_at)
        )
        return result.tuples().all()

    async def get_participation(
        self, occurrence_id: UUID, user_id: UUID
    ) -> EventParticipation | None:
        return await self.session.scalar(
            select(EventParticipation).where(
                EventParticipation.occurrence_id == occurrence_id,
                EventParticipation.user_id == user_id,
            )
        )

    async def topic_slugs(self, event_ids: Iterable[UUID]) -> dict[UUID, list[str]]:
        result = await self.session.execute(
            select(EventTopic.event_id, Topic.slug)
            .join(Topic, Topic.id == EventTopic.topic_id)
            .where(EventTopic.event_id.in_(list(event_ids)))
            .order_by(Topic.slug)
        )
        slugs: dict[UUID, list[str]] = {}
        for event_id, slug in result:
            slugs.setdefault(event_id, []).append(slug)
        return slugs

    async def locations(self, location_ids: Iterable[UUID]) -> dict[UUID, Location]:
        result = await self.session.scalars(
            select(Location).where(Location.id.in_(list(location_ids)))
        )
        return {location.id: location for location in result}

    async def profiles(self, user_ids: Iterable[UUID]) -> dict[UUID, Profile]:
        result = await self.session.scalars(select(Profile).where(Profile.id.in_(list(user_ids))))
        return {profile.id: profile for profile in result}

    async def ensure_topics(self, slugs: Sequence[str]) -> list[UUID]:
        """Return topic IDs for the slugs, creating the topics that do not exist yet."""
        if not slugs:
            return []
        result = await self.session.execute(
            select(Topic.slug, Topic.id).where(Topic.slug.in_(slugs))
        )
        ids = {slug: topic_id for slug, topic_id in result}
        new_topics = [Topic(slug=slug, name=slug) for slug in slugs if slug not in ids]
        if new_topics:
            self.session.add_all(new_topics)
            await self.session.flush()
            ids.update({topic.slug: topic.id for topic in new_topics})
        return [ids[slug] for slug in slugs]

    async def replace_topics(self, event_id: UUID, topic_ids: Iterable[UUID]) -> None:
        await self.session.execute(delete(EventTopic).where(EventTopic.event_id == event_id))
        self.session.add_all(
            EventTopic(event_id=event_id, topic_id=topic_id) for topic_id in topic_ids
        )
        await self.session.flush()

    @staticmethod
    def _select_rows() -> Select:
        return (
            select(Event, EventOccurrence, going_count.label("participants_count"))
            .join(EventOccurrence, EventOccurrence.event_id == Event.id)
            .where(Event.deleted_at.is_(None))
        )

    @staticmethod
    def _local_date(moment):
        """Calendar date of a moment in the occurrence's own time zone."""
        return cast(func.timezone(EventOccurrence.timezone, moment), Date)

    async def _fetch(self, statement: Select) -> list[EventRow]:
        result = await self.session.execute(statement)
        return [EventRow(event, occurrence, count) for event, occurrence, count in result]
