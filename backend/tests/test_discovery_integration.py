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

from dvizh_backend.api.schemas.discovery import DiscoveryRequest
from dvizh_backend.config import Settings
from dvizh_backend.database.models import Event, EventFavorite, EventOccurrence, Location, Profile
from dvizh_backend.database.services.discovery import DiscoveryRepository
from dvizh_backend.services.discovery_service import EventDiscoveryService


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
            assert first.map.total_events == first.feed.total_events == 160
            assert 1 <= len(first.map.items) <= 30
            assert sum(item.count for item in first.map.items) == 160
            free = await discover(viewport=world, filters={"free_only": True})
            assert free.map.total_events == free.feed.total_events == 159
            later = await discover(
                viewport=world,
                filters={"date_from": (now + timedelta(days=3)).date()},
            )
            assert later.map.total_events == later.feed.total_events == 1
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
            assert unscoped.feed.total_events == 161  # Missing coordinates still work in the feed.
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
