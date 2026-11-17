"""Discovery invariants independent of infrastructure and provider availability."""

import asyncio
import math
import random
from collections import defaultdict
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dvizh_backend.api.dependencies import get_discovery_service, get_discovery_viewer
from dvizh_backend.api.routers.discovery import router
from dvizh_backend.api.schemas.discovery import (
    DiscoveryBootstrapResponse,
    DiscoveryFeed,
    DiscoveryRequest,
    DiscoveryResponse,
    MapViewport,
)
from dvizh_backend.config import Settings
from dvizh_backend.services import discovery_service, discovery_tokens
from dvizh_backend.services.discovery_service import EventDiscoveryService
from dvizh_backend.services.discovery_tokens import DiscoveryContextError, DiscoveryTokens
from dvizh_backend.services.map_clustering import MAX_MARKERS, cell_for, cluster_map


class PointRepository:
    """In-memory equivalent of spatial grouping, including the DB's overflow probe."""

    def __init__(self, points):
        self.points = points

    async def groups(self, level, cell=None):
        buckets = defaultdict(list)
        for index, (longitude, latitude) in enumerate(self.points):
            if cell is not None and cell_for(longitude, latitude, cell[0]) != tuple(cell[1:]):
                continue
            buckets[cell_for(longitude, latitude, level)].append((index, longitude, latitude))
        result = []
        for (x, y), members in sorted(buckets.items())[:31]:
            longitudes = [point[1] for point in members]
            latitudes = [point[2] for point in members]
            result.append({
                "level": level, "x": x, "y": y, "count": len(members),
                "event_id": str(UUID(int=members[0][0] + 1)),
                "longitude": math.degrees(math.atan2(
                    sum(math.sin(math.radians(value)) for value in longitudes),
                    sum(math.cos(math.radians(value)) for value in longitudes),
                )),
                "latitude": sum(latitudes) / len(latitudes),
                "west": min(longitudes), "east": max(longitudes),
                "south": min(latitudes), "north": max(latitudes),
            })
        return result


def distribution(kind):
    rng = random.Random(410)
    if kind == "world":
        return [(rng.uniform(-180, 180), rng.uniform(-85, 85)) for _ in range(2000)]
    if kind == "dense":
        return [(30.3 + rng.random() / 50, 59.9 + rng.random() / 50) for _ in range(2000)]
    if kind == "skewed":
        return distribution("dense") + [(value, value / 4) for value in range(-170, 171, 10)]
    return [(139.65, 35.67)] * 2000


@pytest.mark.parametrize("kind", ["world", "dense", "skewed", "same-point"])
@pytest.mark.parametrize("zoom", [0, 5.75, 13, 24])
def test_clusters_bound_marker_count_and_partition_every_event(kind, zoom):
    points = distribution(kind)
    result = asyncio.run(cluster_map(PointRepository(points), zoom))
    assert 0 < len(result) <= MAX_MARKERS
    assert sum(group["count"] for group in result) == len(points)
    for longitude, latitude in points:
        matching = [group for group in result if cell_for(
            longitude, latitude, group["level"]
        ) == (group["x"], group["y"])]
        assert len(matching) == 1, "Every eligible event must belong to exactly one visible object"
    assert result == asyncio.run(cluster_map(PointRepository(points), zoom))


def test_identical_location_stays_one_cluster_at_maximum_zoom():
    groups = asyncio.run(cluster_map(PointRepository([(30.0, 60.0)] * 100), 24))
    assert len(groups) == 1
    assert groups[0]["count"] == 100
    assert groups[0]["longitude"] == pytest.approx(30)
    assert groups[0]["latitude"] == 60
    assert asyncio.run(cluster_map(PointRepository([]), 24)) == []


@pytest.mark.parametrize("longitude,latitude", [(-180, -90), (180, 90), (-180, 90), (180, -90)])
def test_cell_coordinates_remain_in_world_at_poles_and_dateline(longitude, latitude):
    for level in [0, 1, 12, 24]:
        x, y = cell_for(longitude, latitude, level)
        assert 0 <= x < 2 ** level
        assert 0 <= y < 2 ** level


def test_tokens_bind_purpose_key_expiry_and_payload(monkeypatch):
    now = [1000]
    monkeypatch.setattr(discovery_tokens.time, "time", lambda: now[0])
    signer = DiscoveryTokens("unit-test-discovery-key", ttl=60)
    data = {"cell": [12, 123, 456], "filters": "criteria-hash"}
    token = signer.encode("cluster", data)
    assert signer.decode("cluster", token) == data
    encoded, signature = token.split(".")
    altered = ("A" if encoded[0] != "A" else "B") + encoded[1:] + "." + signature
    for purpose, value, verifier in [
        ("cursor", token, signer),
        ("cluster", altered, signer),
        ("cluster", token, DiscoveryTokens("another-key")),
        ("cluster", "not-a-token", signer),
    ]:
        with pytest.raises(DiscoveryContextError):
            verifier.decode(purpose, value)
    now[0] += 60
    with pytest.raises(DiscoveryContextError):
        signer.decode("cluster", token)


def viewport(longitude=30, latitude=60):
    return MapViewport(
        west=longitude - 1, east=longitude + 1, south=latitude - 1, north=latitude + 1,
        zoom=12, center={"longitude": longitude, "latitude": latitude},
    )


def test_selection_freezes_feed_scope_but_map_follows_current_viewport(monkeypatch):
    repositories = []

    class Repository:
        def __init__(self, session, filters, as_of, scope):
            self.scope = scope
            self.filters = filters
            self.as_of = as_of
            self.feed = AsyncMock(return_value=([], 2, False))
            repositories.append(self)

    marker = {
        "level": 0, "x": 0, "y": 0, "count": 2, "event_id": str(uuid4()),
        "longitude": 30.0, "latitude": 60.0,
        "west": 30.0, "east": 30.0, "south": 60.0, "north": 60.0,
    }
    monkeypatch.setattr(discovery_service, "DiscoveryRepository", Repository)
    monkeypatch.setattr(discovery_service, "cluster_map", AsyncMock(return_value=[marker]))
    settings = Settings(_env_file=None, discovery_token_secret="discovery-unit-test-" * 3)
    service = EventDiscoveryService(AsyncMock(), settings)

    async def scenario():
        first_view = viewport()
        first = await service.discover(DiscoveryRequest(viewport=first_view), None)
        token = first.map.items[0].selection_token
        assert token
        repositories.clear()
        current_view = viewport(80, 30)
        selected = await service.discover(
            DiscoveryRequest(viewport=current_view, selection_token=token), None,
        )
        feed_repository, map_repository = repositories
        assert feed_repository.scope == first_view
        assert feed_repository.feed.call_args.args[1] == first_view.center
        assert feed_repository.feed.call_args.args[-1] == [0, 0, 0]
        assert map_repository.scope == current_view
        assert selected.as_of == first.as_of
        assert selected.feed.total_events == 2
        with pytest.raises(DiscoveryContextError):
            await service.discover(DiscoveryRequest(
                viewport=current_view, selection_token=token, filters={"q": "different"},
            ), None)
        invalid_cursor = service.tokens.encode("cursor", {
            "context": "another-query", "as_of": datetime.now(UTC).isoformat(), "after": [],
        })
        with pytest.raises(DiscoveryContextError):
            await service.discover(
                DiscoveryRequest(viewport=first_view, cursor=invalid_cursor), None,
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["viewer_id", "friends_of"])
def test_discovery_never_accepts_a_spoofed_actor(field):
    app = FastAPI()
    app.include_router(router)
    service = SimpleNamespace(discover=AsyncMock())
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_discovery_viewer] = lambda: None
    with TestClient(app) as http:
        response = http.post("/api/events/discovery", json={"filters": {field: str(uuid4())}})
    assert response.status_code == 403
    service.discover.assert_not_awaited()


def test_discovery_sets_private_no_store_for_a_valid_read():
    app = FastAPI()
    app.include_router(router)
    response = DiscoveryResponse(
        as_of=datetime.now(UTC), feed=DiscoveryFeed(items=[], total_events=0),
    )
    service = SimpleNamespace(discover=AsyncMock(return_value=response))
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_discovery_viewer] = lambda: None
    with TestClient(app) as http:
        result = http.post("/api/events/discovery", json={})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.json()["feed"] == {"items": [], "total_events": 0, "next_cursor": None}


def test_bootstrap_validates_origin_and_actors_without_accepting_a_viewport():
    app = FastAPI()
    app.include_router(router)
    service = SimpleNamespace(bootstrap=AsyncMock(
        return_value=DiscoveryBootstrapResponse(nearest=None),
    ))
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_discovery_viewer] = lambda: None
    body = {"origin": {"longitude": 30, "latitude": 60}, "filters": {"q": "#поход"}}
    with TestClient(app) as http:
        response = http.post("/api/events/discovery/bootstrap", json=body)
        assert response.status_code == 200
        assert response.json() == {"nearest": None}
        assert response.headers["cache-control"] == "private, no-store"
        assert service.bootstrap.call_args.args[0].filters.q == "#поход"
        for field in ("viewer_id", "friends_of"):
            response = http.post("/api/events/discovery/bootstrap", json={
                **body, "filters": {field: str(uuid4())},
            })
            assert response.status_code == 403
        for invalid in ({}, {**body, "viewport": {}}, {"origin": {"latitude": 91, "longitude": 0}}):
            assert http.post("/api/events/discovery/bootstrap", json=invalid).status_code == 422
        assert service.bootstrap.await_count == 1


@pytest.mark.parametrize("bad", [
    {"west": 0, "east": 0, "south": 0, "north": 1},
    {"west": 0, "east": 1, "south": 0, "north": 0},
    {"west": -181, "east": 1, "south": 0, "north": 1},
    {"west": 0, "east": 1, "south": float("nan"), "north": 1},
])
def test_viewport_rejects_degenerate_and_non_finite_areas(bad):
    with pytest.raises(ValidationError):
        MapViewport(**bad, zoom=10, center={"longitude": 0, "latitude": 0})
