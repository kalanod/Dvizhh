"""Сортировки ленты GET /api/events: SQL без базы и порядок на настоящей схеме."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from dvizh_backend.api.dependencies import get_event_service
from dvizh_backend.database.models import (
    Event,
    EventDismissal,
    EventFavorite,
    EventOccurrence,
    EventParticipation,
    EventTag,
    Location,
    Profile,
    Tag,
    TagCategory,
)
from dvizh_backend.database.services.event_queries import EventQueryService
from dvizh_backend.database.services.event_sorting import SORTINGS, SortContext
from dvizh_backend.database.services.exceptions import EventSortError
from dvizh_backend.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
SPB = (59.9386, 30.3141)
PUSHKIN = (59.7240, 30.4134)  # ~25 км
MOSCOW = (55.7558, 37.6173)  # ~630 км


def order_by_sql(sort: str, **context) -> str:
    """ORDER BY, который EventQueryService отправит в PostgreSQL."""
    captured = {}

    async def fetch(statement):
        captured["statement"] = statement
        return []

    queries = EventQueryService(MagicMock())
    queries._fetch = fetch
    asyncio.run(queries.list_public(sort=sort, **context))
    sql = str(captured["statement"].compile(dialect=postgresql.dialect()))
    return sql[sql.index("ORDER BY") :]


def test_every_sorting_is_registered_under_its_name():
    assert set(SORTINGS) == {"relevance", "novelty", "title", "distance", "start"}
    assert all(name == sorting.name for name, sorting in SORTINGS.items())


@pytest.mark.parametrize(
    ("sort", "context", "first_key"),
    [
        ("novelty", {}, "ORDER BY events.published_at DESC NULLS LAST"),
        ("title", {}, "ORDER BY lower(events.title) ASC NULLS LAST, events.title ASC NULLS LAST"),
        ("distance", {"latitude": 59.93, "longitude": 30.31}, "ORDER BY CAST((SELECT ST_Distance"),
        ("relevance", {}, "ORDER BY "),
        ("start", {}, "ORDER BY event_occurrences.starts_at ASC NULLS LAST"),
    ],
)
def test_sorting_keys_come_before_the_shared_tie_breakers_and_limit(sort, context, first_key):
    sql = order_by_sql(sort, **context)
    assert sql.startswith(first_key)
    assert "event_occurrences.starts_at, events.id" in sql
    assert "LIMIT" in sql


def test_distance_without_any_point_explains_what_to_do():
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    with pytest.raises(EventSortError, match="широту и долготу в профиле"):
        asyncio.run(SORTINGS["distance"].order_by(SortContext(session, None, None, None)))
    with pytest.raises(EventSortError, match="вместе"):
        asyncio.run(SORTINGS["distance"].order_by(SortContext(session, None, 59.9, None)))


def test_distance_falls_back_to_the_profile_point():
    session = MagicMock()
    session.get = AsyncMock(
        return_value=MagicMock(latitude=Decimal("59.938600"), longitude=Decimal("30.314100"))
    )
    keys = asyncio.run(SORTINGS["distance"].order_by(SortContext(session, uuid4(), None, None)))
    assert "59.9386" in str(keys[0].compile(compile_kwargs={"literal_binds": True}))


def request_events(service, query: str) -> httpx.Response:
    async def scenario() -> httpx.Response:
        overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_event_service] = lambda: service
        try:
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                return await http.get(f"/api/events?{query}")
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides)

    return asyncio.run(scenario())


def test_events_endpoint_passes_sort_and_point():
    service = MagicMock()
    service.list_public = AsyncMock(return_value=[])

    response = request_events(
        service, "sort=distance&latitude=59.93&longitude=30.31&free_only=true"
    )

    assert response.status_code == 200
    call = service.list_public.await_args.kwargs
    assert (call["sort"], call["latitude"], call["longitude"]) == ("distance", 59.93, 30.31)
    assert call["free_only"] is True


@pytest.mark.parametrize("query", ["sort=popularity", "sort=distance&latitude=91&longitude=0"])
def test_events_endpoint_rejects_unknown_sort_and_bad_point(query):
    service = MagicMock()
    service.list_public = AsyncMock()

    assert request_events(service, query).status_code == 422
    service.list_public.assert_not_awaited()


def test_events_endpoint_returns_sort_errors_as_json():
    service = MagicMock()
    service.list_public = AsyncMock(
        side_effect=EventSortError("Передайте latitude и longitude вместе.")
    )

    response = request_events(service, "sort=distance")

    assert response.status_code == 422
    assert response.json() == {"detail": "Передайте latitude и longitude вместе."}


@pytest.mark.parametrize("field", ["viewer_id", "friends_of"])
def test_legacy_feed_cannot_bypass_discovery_identity_checks(field):
    service = MagicMock()
    service.list_public = AsyncMock()
    response = request_events(service, f"sort=relevance&{field}={uuid4()}")
    assert response.status_code == 403
    service.list_public.assert_not_awaited()


integration = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires PostgreSQL")


class Catalog:
    """Тестовые записи в транзакции, которая откатывается после теста."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.now = datetime.now(UTC)

    async def profile(self, point: tuple[float, float] | None = None) -> UUID:
        profile = Profile(
            id=uuid4(),
            username=f"sort_{uuid4().hex[:20]}",
            display_name="Test user",
            latitude=point and Decimal(str(point[0])),
            longitude=point and Decimal(str(point[1])),
        )
        self.session.add(profile)
        await self.session.flush()
        return profile.id

    async def tag(self) -> UUID:
        category = TagCategory(name=f"sort-{uuid4().hex}", color="#123456")
        self.session.add(category)
        await self.session.flush()
        tag = Tag(category_id=category.id, slug=f"sort-{uuid4().hex}", name="Test")
        self.session.add(tag)
        await self.session.flush()
        return tag.id

    async def event(
        self,
        organizer: UUID,
        tags: tuple[UUID, ...],
        *,
        title: str = "Test event",
        published_ago: timedelta = timedelta(hours=1),
        point: tuple[float, float] | None = None,
    ) -> tuple[UUID, UUID]:
        location_id = None
        if point is not None:
            location = Location(latitude=Decimal(str(point[0])), longitude=Decimal(str(point[1])))
            self.session.add(location)
            await self.session.flush()
            location_id = location.id
        event = Event(
            slug=f"sort-{uuid4().hex}",
            title=title,
            description="Test",
            origin="USER",
            status="PUBLISHED",
            visibility="PUBLIC",
            format="OFFLINE" if point else "ONLINE",
            online_url=None if point else "https://example.invalid/test",
            location_id=location_id,
            organizer_user_id=organizer,
            published_at=self.now - published_ago,
        )
        self.session.add(event)
        await self.session.flush()
        starts = self.now + timedelta(days=3)
        occurrence = EventOccurrence(
            event_id=event.id,
            starts_at=starts,
            ends_at=starts + timedelta(hours=2),
            timezone="UTC",
            status="SCHEDULED",
        )
        self.session.add(occurrence)
        self.session.add_all(EventTag(event_id=event.id, tag_id=tag) for tag in tags)
        await self.session.flush()
        return event.id, occurrence.id


def run_in_rollback(scenario) -> None:
    async def run() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
            try:
                await scenario(Catalog(session), EventQueryService(session))
            finally:
                await session.close()
                await transaction.rollback()
        await engine.dispose()

    asyncio.run(run())


def ids(rows) -> list[UUID]:
    return [row.event.id for row in rows]


@integration
def test_title_novelty_and_distance_on_real_schema():
    async def scenario(catalog: Catalog, queries: EventQueryService) -> None:
        user = await catalog.profile(point=SPB)
        only_ours = await catalog.tag()
        running, _ = await catalog.event(
            user, (only_ours,), title="бег", published_ago=timedelta(hours=3), point=MOSCOW
        )
        art, _ = await catalog.event(
            user, (only_ours,), title="Арт", published_ago=timedelta(hours=1), point=SPB
        )
        online, _ = await catalog.event(
            user, (only_ours,), title="арт онлайн", published_ago=timedelta(hours=2)
        )
        nearby, _ = await catalog.event(
            user, (only_ours,), title="Ярмарка", published_ago=timedelta(hours=4), point=PUSHKIN
        )

        async def order(sort: str, **point) -> list[UUID]:
            return ids(await queries.list_public(tag_id=only_ours, sort=sort, limit=10, **point))

        assert await order("title") == [art, online, running, nearby]
        assert await order("novelty") == [art, online, running, nearby]
        moscow = {"latitude": MOSCOW[0], "longitude": MOSCOW[1]}
        assert await order("distance", **moscow) == [running, nearby, art, online]
        from_profile = await queries.list_public(
            tag_id=only_ours, sort="distance", viewer_id=user, limit=2
        )
        assert ids(from_profile) == [art, nearby]

    run_in_rollback(scenario)


@integration
def test_relevance_prefers_the_viewers_topics():
    async def scenario(catalog: Catalog, queries: EventQueryService) -> None:
        organizer, user = await catalog.profile(), await catalog.profile()
        only_ours, music, sport = await catalog.tag(), await catalog.tag(), await catalog.tag()
        liked, liked_occurrence = await catalog.event(organizer, (only_ours, music))
        catalog.session.add_all(
            [
                EventParticipation(occurrence_id=liked_occurrence, user_id=user, status="GOING"),
                EventFavorite(user_id=user, event_id=liked),
            ]
        )
        concert, _ = await catalog.event(
            organizer, (only_ours, music), published_ago=timedelta(days=10)
        )
        match, _ = await catalog.event(organizer, (only_ours, sport), published_ago=timedelta(0))
        boring, _ = await catalog.event(organizer, (only_ours, sport), published_ago=timedelta(0))
        catalog.session.add(EventDismissal(user_id=user, event_id=boring))
        await catalog.session.flush()

        personal = ids(
            await queries.list_public(tag_id=only_ours, sort="relevance", viewer_id=user)
        )
        cold_start = ids(await queries.list_public(tag_id=only_ours, sort="relevance"))

        # The older music event beats today's sport event; the dismissed one is hidden.
        assert personal.index(concert) < personal.index(match)
        assert boring not in personal
        # Without history: popularity and freshness only.
        assert cold_start[0] == liked
        assert cold_start.index(match) < cold_start.index(concert)

    run_in_rollback(scenario)
