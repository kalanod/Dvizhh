"""Database projections of the shared discovery candidate set; never truncate candidates."""

from datetime import datetime
from math import pi
from uuid import UUID

from sqlalchemy import Date, Float, String, and_, case, cast, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.discovery import DiscoveryFilters, MapViewport
from dvizh_backend.database.geo import GeographyPoint
from dvizh_backend.database.models import (
    Event,
    EventOccurrence,
    EventParticipation,
    Friendship,
    Location,
)
from dvizh_backend.database.models.enums import FriendshipStatus, ParticipationStatus

from .event_queries import EventQueryService

MAX_LATITUDE = 85.0511287798066


def grid_expressions(columns, level: int):
    scale = 2**level
    latitude = func.greatest(-MAX_LATITUDE, func.least(MAX_LATITUDE, columns.latitude))
    radians = func.radians(latitude)
    x = func.least(scale - 1, func.floor((columns.longitude + 180) / 360 * scale))
    y = func.least(
        scale - 1,
        func.greatest(
            0, func.floor((1 - func.ln(func.tan(radians) + 1 / func.cos(radians)) / pi) / 2 * scale)
        ),
    )
    return x, y


def viewport_predicate(position, viewport: MapViewport):
    def area(west, east):
        return func.ST_Covers(
            func.ST_MakeEnvelope(west, viewport.south, east, viewport.north, 4326), position
        )

    if viewport.west > viewport.east:
        return or_(area(viewport.west, 180), area(-180, viewport.east))
    return area(viewport.west, viewport.east)


class DiscoveryRepository:
    def __init__(
        self,
        session: AsyncSession,
        filters: DiscoveryFilters,
        as_of: datetime,
        viewport: MapViewport | None,
    ):
        self.session = session
        self.viewport = viewport
        query = EventQueryService(session)
        statement = query.public_statement(
            text_query=filters.q or None,
            tag_id=filters.tag_id,
            date_from=filters.date_from,
            date_to=filters.date_to,
            free_only=filters.free_only,
            available_only=filters.available_only,
            viewer_id=filters.viewer_id,
        ).outerjoin(Location, Location.id == Event.location_id)
        end = func.coalesce(EventOccurrence.ends_at, EventOccurrence.starts_at)
        local_today = cast(func.timezone(EventOccurrence.timezone, as_of), Date)
        local_start = query._local_date(EventOccurrence.starts_at)
        statement = statement.where(
            or_(
                end >= as_of,
                and_(EventOccurrence.is_all_day, local_start == local_today),
            )
        )
        if viewport is not None:
            statement = statement.where(
                Location.position.is_not(None), viewport_predicate(Location.position, viewport)
            )
        friends = 0
        if filters.friends_of is not None:
            user_id = filters.friends_of
            friend_ids = select(
                case(
                    (Friendship.user_low_id == user_id, Friendship.user_high_id),
                    else_=Friendship.user_low_id,
                )
            ).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(
                    Friendship.user_low_id == user_id,
                    Friendship.user_high_id == user_id,
                ),
            )
            friends = (
                select(func.count(EventParticipation.id))
                .where(
                    EventParticipation.occurrence_id == EventOccurrence.id,
                    EventParticipation.status == ParticipationStatus.GOING,
                    EventParticipation.user_id.in_(friend_ids),
                )
                .correlate(EventOccurrence)
                .scalar_subquery()
            )
        # Only eligible occurrences participate. One canonical row per event, before counts/limits.
        eligible = statement.with_only_columns(
            Event.id.label("event_id"),
            EventOccurrence.id.label("occurrence_id"),
            EventOccurrence.starts_at.label("starts_at"),
            func.coalesce(Event.published_at, Event.created_at).label("published_at"),
            cast(Location.latitude, Float).label("latitude"),
            cast(Location.longitude, Float).label("longitude"),
            Location.position.label("position"),
            (-friends if filters.friends_of is not None else literal(0)).label("friends_rank"),
            func.row_number()
            .over(
                partition_by=Event.id,
                order_by=(
                    case((EventOccurrence.starts_at <= as_of, 0), else_=1),
                    EventOccurrence.starts_at,
                    EventOccurrence.id,
                ),
            )
            .label("choice"),
        ).subquery("discovery_eligible")
        self.candidates = (
            select(eligible).where(eligible.c.choice == 1).subquery("discovery_events")
        )

    @staticmethod
    async def begin_snapshot(session: AsyncSession) -> None:
        from sqlalchemy import text

        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))

    def cell_predicate(self, cell):
        x, y = grid_expressions(self.candidates.c, cell[0])
        return and_(x == cell[1], y == cell[2])

    async def groups(self, level: int, cell=None):
        c = self.candidates.c
        x, y = grid_expressions(c, level)
        statement = select(
            x.label("x"),
            y.label("y"),
            func.count().label("count"),
            func.min(c.event_id.cast(String)).label("event_id"),
            func.avg(c.latitude).label("latitude"),
            func.degrees(
                func.atan2(
                    func.avg(func.sin(func.radians(c.longitude))),
                    func.avg(func.cos(func.radians(c.longitude))),
                )
            ).label("longitude"),
            func.min(c.longitude).label("west"),
            func.max(c.longitude).label("east"),
            func.min(c.latitude).label("south"),
            func.max(c.latitude).label("north"),
        ).where(c.position.is_not(None))
        if cell is not None:
            statement = statement.where(self.cell_predicate(cell))
        # 31 is only an overflow probe. An overflowing result is never sent to the browser.
        result = await self.session.execute(statement.group_by(x, y).order_by(x, y).limit(31))
        return [dict(row, level=level) for row in result.mappings()]

    async def feed(self, sort: str, center, limit: int, after=None, cell=None):
        c = self.candidates.c
        if sort == "distance" and center is not None:
            origin = func.ST_SetSRID(func.ST_MakePoint(center.longitude, center.latitude), 4326)
            score = func.ST_Distance(
                cast(c.position, GeographyPoint()), cast(origin, GeographyPoint())
            )
        elif sort == "start":
            score = func.extract("epoch", c.starts_at)
        else:
            score = -func.extract("epoch", c.published_at)
        score = cast(score, Float)
        statement = select(
            c.occurrence_id, c.event_id, c.starts_at, c.friends_rank, score.label("score")
        )
        where = self.cell_predicate(cell) if cell is not None else None
        count_query = select(func.count()).select_from(self.candidates)
        if where is not None:
            statement = statement.where(where)
            count_query = count_query.where(where)
        if after is not None:
            statement = statement.where(
                tuple_(c.friends_rank, score, c.starts_at, c.event_id)
                > tuple_(after[0], after[1], datetime.fromisoformat(after[2]), UUID(after[3]))
            )
        statement = statement.order_by(c.friends_rank, score, c.starts_at, c.event_id).limit(
            limit + 1
        )
        rows = list((await self.session.execute(statement)).mappings())
        total = await self.session.scalar(count_query)
        return rows[:limit], int(total or 0), len(rows) > limit
