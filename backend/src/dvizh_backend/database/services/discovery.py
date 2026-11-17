"""Database projections of the shared discovery candidate set; never truncate candidates."""

from dataclasses import replace
from datetime import datetime
from math import pi
from uuid import UUID

from sqlalchemy import Date, Float, String, and_, case, cast, exists, func, literal, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.discovery import DiscoveryFilters, MapPoint, MapViewport
from dvizh_backend.database.models import (
    Event,
    EventFavorite,
    EventOccurrence,
    EventParticipation,
    Friendship,
    Location,
)
from dvizh_backend.database.models.enums import (
    FriendshipStatus,
    MapMarkerPriority,
    ParticipationStatus,
)

from .event_queries import EventQueryService, going_count
from .event_sorting import SORTINGS, DistanceSorting, SortContext, SortKey
from .exceptions import EventSortError

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
        self.filters = filters
        self.as_of = as_of
        self.ranking: dict = {}
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
        priority = literal(MapMarkerPriority.DEFAULT.value)
        if filters.viewer_id is not None:
            favorite = exists().where(
                EventFavorite.event_id == Event.id,
                EventFavorite.user_id == filters.viewer_id,
            ).correlate(Event)
            going = exists().where(
                EventParticipation.occurrence_id == EventOccurrence.id,
                EventParticipation.user_id == filters.viewer_id,
                EventParticipation.status == ParticipationStatus.GOING,
            ).correlate(EventOccurrence)
            priority = case(
                (favorite, MapMarkerPriority.FAVORITE.value),
                (Event.organizer_user_id == filters.viewer_id, MapMarkerPriority.ORGANIZER.value),
                (going, MapMarkerPriority.GOING.value),
                else_=MapMarkerPriority.DEFAULT.value,
            )
        # Only eligible occurrences participate. One canonical row per event, before counts/limits.
        eligible = statement.with_only_columns(
            Event.id.label("event_id"),
            EventOccurrence.id.label("occurrence_id"),
            EventOccurrence.starts_at.label("starts_at"),
            Event.published_at.label("published_at"),
            Event.created_at.label("created_at"),
            Event.title.label("title"),
            func.max(priority).over(partition_by=Event.id).label("marker_priority"),
            going_count.label("going_count"),
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
            func.min(c.title).label("title"),
            func.max(c.marker_priority).label("marker_priority"),
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

    async def nearest(self, origin: MapPoint) -> RowMapping | None:
        c = self.candidates.c
        context = SortContext(
            self.session, self.filters.viewer_id, origin.latitude, origin.longitude,
            as_of=self.as_of, columns=c,
        )
        distance = (await SORTINGS["distance"].keys(context))[0].expression
        statement = (
            select(c.event_id, c.latitude, c.longitude)
            .where(c.position.is_not(None))
            .order_by(distance, c.event_id)
            .limit(1)
        )
        return (await self.session.execute(statement)).mappings().first()

    async def feed(self, sort: str, center, limit: int, after=None, cell=None, *, ranking=None):
        c = self.candidates.c
        context = SortContext(
            self.session,
            self.filters.viewer_id,
            center.latitude if center else None,
            center.longitude if center else None,
            as_of=self.as_of,
            columns=c,
        )
        self.ranking = ranking or {}
        if sort == "distance":
            if ranking and "origin" in ranking:
                latitude, longitude = ranking["origin"]
            else:
                latitude, longitude = await DistanceSorting._origin(context)
            context = replace(context, latitude=latitude, longitude=longitude)
            self.ranking = {"origin": [latitude, longitude]}
        if sort == "relevance":
            if ranking is not None:
                interest = {UUID(tag): weight for tag, weight in ranking["interest"].items()}
            else:
                interest = await SORTINGS[sort]._interest(context)
            context = replace(context, interest=interest)
            self.ranking = {"interest": {str(tag): weight for tag, weight in interest.items()}}
        keys = [
            SortKey(c.friends_rank),
            *await SORTINGS[sort].keys(context),
            SortKey(c.starts_at, "datetime"),
            SortKey(c.event_id, "uuid"),
        ]
        statement = select(
            c.occurrence_id,
            c.event_id,
            c.starts_at,
            *(key.expression.label(f"sort_{index}") for index, key in enumerate(keys)),
        )
        where = self.cell_predicate(cell) if cell is not None else None
        count_query = select(func.count()).select_from(self.candidates)
        if where is not None:
            statement = statement.where(where)
            count_query = count_query.where(where)
        if after is not None:
            try:
                if len(after) != len(keys):
                    raise ValueError("Invalid ordering cursor")
                values = [key.decode(value) for key, value in zip(keys, after, strict=True)]
                statement = statement.where(
                    or_(
                        *(
                            and_(
                                *(
                                    keys[previous].equal_to(values[previous])
                                    for previous in range(index)
                                ),
                                key.after(values[index]),
                            )
                            for index, key in enumerate(keys)
                        )
                    )
                )
            except (ValueError, TypeError, AttributeError):
                raise EventSortError("Порядок выдачи изменился. Обновите ленту.") from None
        statement = statement.order_by(*(key.order_by() for key in keys)).limit(limit + 1)
        rows = [dict(row) for row in (await self.session.execute(statement)).mappings()]
        for row in rows:
            row["after"] = [key.encode(row[f"sort_{index}"]) for index, key in enumerate(keys)]
        total = await self.session.scalar(count_query)
        return rows[:limit], int(total or 0), len(rows) > limit
