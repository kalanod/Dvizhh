"""Real PostGIS discovery; use only a separately migrated disposable TEST_DATABASE_URL."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_event_sorting import Catalog, run_in_rollback

from dvizh_backend.api.schemas.discovery import DiscoveryBootstrapRequest, DiscoveryRequest
from dvizh_backend.config import Settings
from dvizh_backend.database.models import (
    Event,
    EventFavorite,
    EventOccurrence,
    EventParticipation,
    Location,
    Profile,
)
from dvizh_backend.database.services.discovery import DiscoveryRepository
from dvizh_backend.services.discovery_service import EventDiscoveryService
from dvizh_backend.services.event_service import EventService


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
def test_marker_priority_aggregates_the_whole_group_and_updates_after_personal_changes():
    async def scenario(catalog: Catalog, _queries):
        viewer, other = await catalog.profile(), await catalog.profile()
        scope, solo = await catalog.tag(), await catalog.tag()
        regular, _ = await catalog.event(other, (scope,), title="A regular", point=(60, 30))
        _, going_occurrence = await catalog.event(
            other, (scope,), title="B going", point=(60, 30),
        )
        owned, _ = await catalog.event(viewer, (scope,), title="C organizer", point=(60, 30))
        favorite, favorite_occurrence = await catalog.event(
            viewer, (scope, solo), title="Z favorite", point=(60, 30),
        )
        catalog.session.add(EventFavorite(user_id=viewer, event_id=favorite))
        participations = [EventParticipation(
            user_id=viewer, occurrence_id=occurrence, status="GOING",
        ) for occurrence in (going_occurrence, favorite_occurrence)]
        catalog.session.add_all(participations)
        await catalog.session.flush()
        service = EventDiscoveryService(catalog.session, Settings(
            _env_file=None, discovery_token_secret="marker-priority-test-" * 2,
        ))
        request = DiscoveryRequest(
            filters={"tag_id": scope}, sort="title", limit=1,
            viewport=dict(west=29, east=31, south=59, north=61, zoom=24,
                          center={"longitude": 30, "latitude": 60}),
        )
        result = await service.discover(request, viewer)
        assert result.feed.items[0].id == regular  # Favorite is outside this feed page.
        assert len(result.map.items) == 1
        assert result.map.items[0].count == 4
        assert result.map.items[0].state == "favorite"
        assert result.map.items[0].title is None
        single = await service.discover(request.model_copy(update={
            "filters": request.filters.model_copy(update={"tag_id": solo}),
        }), viewer)
        assert single.map.items[0].state == "favorite"
        assert single.map.items[0].title == "Z favorite"
        assert single.map.items[0].event_id == favorite
        assert (await service.discover(request, None)).map.items[0].state == "default"
        await catalog.session.execute(delete(EventFavorite).where(EventFavorite.user_id == viewer))
        assert (await service.discover(request, viewer)).map.items[0].state == "organizer"
        for event_id in (owned, favorite):
            (await catalog.session.get(Event, event_id)).organizer_user_id = other
        await catalog.session.flush()
        assert (await service.discover(request, viewer)).map.items[0].state == "going"
        for participation in participations:
            participation.status = "CANCELLED"
        await catalog.session.flush()
        assert (await service.discover(request, viewer)).map.items[0].state == "default"

    run_in_rollback(scenario)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
def test_recurring_marker_uses_participation_in_any_eligible_occurrence_without_double_count():
    async def scenario(catalog: Catalog, _queries):
        viewer, other = await catalog.profile(), await catalog.profile()
        scope = await catalog.tag()
        event_id, first = await catalog.event(other, (scope,), point=(60, 30))
        later = EventOccurrence(
            event_id=event_id, starts_at=catalog.now + timedelta(days=6),
            ends_at=catalog.now + timedelta(days=6, hours=2), timezone="UTC", status="SCHEDULED",
        )
        catalog.session.add(later)
        await catalog.session.flush()
        catalog.session.add(EventParticipation(
            user_id=viewer, occurrence_id=later.id, status="GOING",
        ))
        await catalog.session.flush()
        service = EventDiscoveryService(catalog.session, Settings(
            _env_file=None, discovery_token_secret="recurring-marker-test-" * 2,
        ))
        request = DiscoveryRequest(
            filters={"tag_id": scope},
            viewport=dict(west=29, east=31, south=59, north=61, zoom=12,
                          center={"longitude": 30, "latitude": 60}),
        )
        result = await service.discover(request, viewer)
        assert result.map.total_events == result.map.items[0].count == 1
        assert result.map.items[0].state == "going"
        assert result.feed.items[0].occurrence_id == first
        request.filters.date_to = (catalog.now + timedelta(days=4)).date()
        assert (await service.discover(request, viewer)).map.items[0].state == "default"

    run_in_rollback(scenario)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
def test_bootstrap_nearest_uses_shared_visibility_filters_and_personal_exclusions():
    async def scenario(catalog: Catalog, _queries):
        organizer = await catalog.profile()
        topic, other_topic = await catalog.tag(), await catalog.tag()
        matching, _ = await catalog.event(organizer, (topic,), title="#поход", point=(61, 31))
        await catalog.event(organizer, (topic,), title="#поход")  # No exact location.
        await catalog.event(organizer, (other_topic,), title="#поход", point=(60, 30))
        for status in ("DRAFT", "CANCELLED"):
            hidden, _ = await catalog.event(organizer, (topic,), title="#поход", point=(60, 30))
            (await catalog.session.get(Event, hidden)).status = status
        private, _ = await catalog.event(organizer, (topic,), title="#поход", point=(60, 30))
        (await catalog.session.get(Event, private)).visibility = "PRIVATE"
        expired, occurrence_id = await catalog.event(
            organizer, (topic,), title="#поход", point=(60, 30),
        )
        occurrence = await catalog.session.get(EventOccurrence, occurrence_id)
        occurrence.starts_at = catalog.now - timedelta(days=2)
        occurrence.ends_at = catalog.now - timedelta(days=1)
        await catalog.session.flush()
        service = EventDiscoveryService(catalog.session, Settings(
            _env_file=None, discovery_token_secret="bootstrap-integration-test-" * 2,
        ))
        request = DiscoveryBootstrapRequest(
            filters={"q": "#поход", "tag_id": topic}, origin={"latitude": 60, "longitude": 30},
        )
        result = await service.bootstrap(request, None)
        assert result.nearest.event_id == matching
        assert result.nearest.point.latitude == 61
        assert result.nearest.point.longitude == 31
        # Distance is exact, with stable ties, and excludes personally dismissed events.
        await EventService(catalog.session).set_dismissed(matching, organizer, enabled=True)
        assert (await service.bootstrap(request, organizer)).nearest is None
        assert (await service.bootstrap(request.model_copy(update={
            "filters": request.filters.model_copy(update={"q": "#нет_такого"}),
        }), None)).nearest is None

    run_in_rollback(scenario)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
@pytest.mark.parametrize("sort", ["novelty", "title", "distance", "start", "relevance"])
def test_hashtags_share_map_feed_selection_and_pagination(sort):
    async def scenario(catalog: Catalog, _queries):
        organizer = await catalog.profile()
        hashtag = "#слизни_" + uuid4().hex
        first, _ = await catalog.event(organizer, (), title=f"Trip {hashtag}", point=(60, 30))
        second, _ = await catalog.event(
            organizer, (), title=f"({hashtag.upper()}), meetup", point=(60, 30),
        )
        online, _ = await catalog.event(organizer, (), title=f"Online {hashtag}")
        for title in (f"{hashtag}_extra", f"word{hashtag}", f"#{hashtag}"):
            await catalog.event(organizer, (), title=title, point=(60, 30))
        service = EventDiscoveryService(
            catalog.session,
            Settings(_env_file=None, discovery_token_secret="hashtag-discovery-test-" * 2),
        )
        request = DiscoveryRequest(
            filters={"q": hashtag}, sort=sort, limit=1,
            origin={"latitude": 60, "longitude": 30} if sort == "distance" else None,
        )
        unscoped = await service.discover(request.model_copy(update={"limit": 20}), None)
        assert {item.id for item in unscoped.feed.items} == {first, second, online}
        viewport = dict(
            west=29, east=31, south=59, north=61, zoom=12,
            center={"longitude": 30, "latitude": 60},
        )
        scoped = DiscoveryRequest(**{**request.model_dump(), "viewport": viewport})
        page = await service.discover(scoped, None)
        assert page.map.total_events == 2
        assert page.feed.total_events == (None if sort == "relevance" else 2)
        assert len(page.map.items) == 1
        assert page.map.items[0].count == 2
        seen = [item.id for item in page.feed.items]
        token = page.map.items[0].selection_token
        while page.feed.next_cursor:
            page = await service.discover(
                scoped.model_copy(update={"cursor": page.feed.next_cursor}), None,
            )
            seen.extend(item.id for item in page.feed.items)
        assert set(seen) == {first, second}
        assert len(seen) == 2
        selected = await service.discover(
            scoped.model_copy(update={"selection_token": token, "limit": 20}), None,
        )
        assert {item.id for item in selected.feed.items} == {first, second}

    run_in_rollback(scenario)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
@pytest.mark.parametrize("sort", ["novelty", "title", "distance", "start", "relevance"])
def test_discovery_postgis_counts_clusters_filters_recurrence_and_keyset(sort):
    async def scenario():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        prefix = "mapqa" + uuid4().hex
        now = datetime.now(UTC)
        event_ids, location_ids = [], []
        settings = Settings(_env_file=None, discovery_token_secret="discovery-integration-key-" * 2)

        async def discover(**kwargs):
            async with sessions() as session:
                await DiscoveryRepository.begin_snapshot(session)
                criteria = {"q": prefix, **kwargs.pop("filters", {})}
                kwargs.setdefault("sort", sort)
                if sort == "distance" and kwargs.get("viewport") is None:
                    kwargs.setdefault("origin", {"longitude": 30, "latitude": 60})
                request = DiscoveryRequest(filters=criteria, **kwargs)
                return await EventDiscoveryService(session, settings).discover(request, None)

        world = dict(
            west=-180,
            east=180,
            south=-90,
            north=90,
            zoom=3,
            center={"longitude": 30, "latitude": 60},
        )
        try:
            async with sessions.begin() as session:
                # 120 distinct locations plus a dense, inseparable group; all must be counted.
                for index in range(164):
                    location = Location(
                        id=uuid4(),
                        latitude=60 if index >= 120 else -70 + index,
                        longitude=30 if index >= 120 else -170 + index * 2.7,
                    )
                    session.add(location)
                    location_ids.append(location.id)
                    await session.flush()
                    title = f"{prefix if index % 2 else prefix.upper()} {index % 7}"
                    event = Event(
                        id=uuid4(),
                        slug=f"{prefix}-{index}",
                        title=title,
                        description="PostGIS discovery fixture",
                        origin="EXTERNAL",
                        status="PUBLISHED",
                        visibility="PUBLIC",
                        format="OFFLINE",
                        price_type="FREE",
                        location_id=location.id,
                        published_at=now if index % 3 else None,
                    )
                    # Four exclusions: draft, private, expired, unknown coordinates.
                    if index == 160:
                        event.status = "DRAFT"
                    if index == 1:
                        event.price_type = "PAID"
                        event.price_min = 10
                        event.currency = "RUB"
                    if index == 161:
                        event.visibility = "PRIVATE"
                    if index == 163:
                        location.latitude = None
                        location.longitude = None
                        location.address_line = "Address without coordinates"
                    session.add(event)
                    event_ids.append(event.id)
                    await session.flush()
                    for day in [1, 2, 3] if index == 0 else [-2] if index == 162 else [1]:
                        session.add(
                            EventOccurrence(
                                id=uuid4(),
                                event_id=event.id,
                                starts_at=now + timedelta(days=day),
                                timezone="UTC",
                                status="SCHEDULED",
                            )
                        )
            first = await discover(viewport=world, limit=7)
            assert first.map.total_events == 160
            assert first.feed.total_events == (None if sort == "relevance" else 160)
            assert 1 <= len(first.map.items) <= 30
            assert sum(item.count for item in first.map.items) == 160
            free = await discover(viewport=world, filters={"free_only": True})
            assert free.map.total_events == 159
            assert free.feed.total_events == (None if sort == "relevance" else 159)
            later = await discover(
                viewport=world,
                filters={"date_from": (now + timedelta(days=3)).date()},
            )
            assert later.map.total_events == 1
            assert later.feed.total_events == (None if sort == "relevance" else 1)
            assert later.feed.items[0].starts_at == now + timedelta(days=3)
            seen = [item.id for item in first.feed.items]
            cursor = first.feed.next_cursor
            while cursor:
                page = await discover(viewport=world, limit=7, cursor=cursor, include_map=False)
                assert page.map is None
                seen.extend(item.id for item in page.feed.items)
                cursor = page.feed.next_cursor
            assert len(seen) == len(set(seen)) == 160
            assert event_ids[0] in seen  # Three occurrences contribute exactly one card.
            cluster = next(item for item in first.map.items if item.count > 1)
            moved = {
                **world,
                "west": 100,
                "east": 110,
                "south": -1,
                "north": 1,
                "center": {"longitude": 105, "latitude": 0},
            }
            selected = await discover(viewport=moved, selection_token=cluster.selection_token)
            assert selected.feed.total_events == cluster.count
            assert selected.map.total_events == 0
            dense = {
                **world,
                "west": 29.99,
                "east": 30.01,
                "south": 59.99,
                "north": 60.01,
                "zoom": 24,
            }
            exact = await discover(viewport=dense)
            assert len(exact.map.items) == 1
            assert exact.map.items[0].count == 40
            assert exact.map.items[0].type == "cluster"
            unscoped = await discover(viewport=None)
            assert unscoped.feed.total_events == (None if sort == "relevance" else 161)
            async with sessions.begin() as session:
                location = await session.get(Location, location_ids[0])
                location.longitude = 179.9
                location.latitude = 0
            wrapped = {**world, "west": 179, "east": -179, "south": -1, "north": 1}
            crossing = await discover(viewport=wrapped)
            assert crossing.map.total_events == 1  # Generated point updates with coordinates.
        finally:
            async with sessions.begin() as session:
                await session.execute(delete(Event).where(Event.id.in_(event_ids)))
                await session.execute(delete(Location).where(Location.id.in_(location_ids)))
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostGIS")
@pytest.mark.parametrize("sort", ["relevance", "distance"])
def test_pagination_freezes_personal_interest_and_profile_origin(sort):
    async def scenario(catalog: Catalog, _queries):
        viewer = await catalog.profile(point=(60, 30))
        organizer = await catalog.profile()
        scope, music, sport = await catalog.tag(), await catalog.tag(), await catalog.tag()
        training, _ = await catalog.event(organizer, (music,))
        catalog.session.add(EventFavorite(user_id=viewer, event_id=training))
        for index in range(8):
            await catalog.event(
                organizer,
                (scope, music if index % 2 else sport),
                title=f"Page {index}",
                point=(60, 30) if index % 2 else (55.75, 37.6),
            )
        await catalog.session.flush()
        service = EventDiscoveryService(
            catalog.session,
            Settings(
                _env_file=None,
                discovery_token_secret="personal-cursor-integration-" * 2,
            ),
            cities=SimpleNamespace(
                coordinates=AsyncMock(
                    return_value=(
                        SimpleNamespace(latitude=60, longitude=30),
                        "SPB",
                    )
                )
            ),
        )
        request = DiscoveryRequest(sort=sort, filters={"tag_id": scope}, limit=2)
        first = await service.discover(request, viewer)
        complete = await service.discover(request.model_copy(update={"limit": 50}), viewer)
        before = service.tokens.decode("cursor", first.feed.next_cursor)
        assert before["ranking"]["interest" if sort == "relevance" else "origin"]
        # A new preference/profile point must not silently change a running cursor's ordering.
        await catalog.session.execute(delete(EventFavorite).where(EventFavorite.user_id == viewer))
        profile = await catalog.session.get(Profile, viewer)
        profile.city = "Moscow"
        service.cities.coordinates.return_value = (
            SimpleNamespace(latitude=55.75, longitude=37.6),
            "Moscow",
        )
        await catalog.session.flush()
        await catalog.session.refresh(profile)
        seen = [item.id for item in first.feed.items]
        cursor = first.feed.next_cursor
        while cursor:
            page = await service.discover(request.model_copy(update={"cursor": cursor}), viewer)
            seen.extend(item.id for item in page.feed.items)
            cursor = page.feed.next_cursor
            if cursor:
                current = service.tokens.decode("cursor", cursor)
                assert current["ranking"] == before["ranking"]
                assert current["as_of"] == before["as_of"]
        assert seen == [item.id for item in complete.feed.items]
        assert len(seen) == len(set(seen)) == 8

    run_in_rollback(scenario)
