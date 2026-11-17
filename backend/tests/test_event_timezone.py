import asyncio
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dvizh_backend.api.dependencies import get_discovery_viewer, get_timezone_service
from dvizh_backend.api.routers.maps import router
from dvizh_backend.api.schemas.timezone import EventTimezoneRequest, PlaceCoordinates
from dvizh_backend.services import yandex_maps_client
from dvizh_backend.services.errors import UserInactiveError, UserNotFoundError
from dvizh_backend.services.event_timezone_service import (
    CoordinateTimezoneResolver,
    EventTimezoneService,
)
from dvizh_backend.services.place_geocoding import ProfileCityGeocoder


def request(place=None, user_id=None, device_timezone="Europe/London") -> EventTimezoneRequest:
    return EventTimezoneRequest(place=place, user_id=user_id, device_timezone=device_timezone)


def service(profile=None):
    users = SimpleNamespace(get_profile=AsyncMock(return_value=profile))
    cities = SimpleNamespace(coordinates=AsyncMock(return_value=None))
    return EventTimezoneService(users, cities)


@pytest.mark.parametrize("latitude,longitude,expected", [
    (35.6762, 139.6503, "Asia/Tokyo"),
    (55.7558, 37.6173, "Europe/Moscow"),
    (59.9391, 30.3159, "Europe/Moscow"),
])
def test_offline_polygon_lookup_uses_actual_coordinates(latitude, longitude, expected):
    assert asyncio.run(CoordinateTimezoneResolver().resolve(PlaceCoordinates(
        latitude=latitude, longitude=longitude
    ))) == expected


def test_place_precedes_profile_and_profile_coordinates_precede_city():
    async def scenario():
        application = service(SimpleNamespace(latitude=55.7558, longitude=37.6173, city="Москва"))
        result = await application.resolve(request(
            place=PlaceCoordinates(latitude=35.6762, longitude=139.6503), user_id=uuid4()
        ))
        assert result.model_dump() == {"timezone": "Asia/Tokyo", "source": "place", "city": None}
        application.users.get_profile.assert_not_awaited()
        result = await application.resolve(request(user_id=uuid4()))
        assert result.model_dump() == {
            "timezone": "Europe/Moscow", "source": "profile_coordinates", "city": "Москва"
        }
        application.cities.coordinates.assert_not_awaited()

    asyncio.run(scenario())


def test_profile_city_uses_geocoded_point_and_structured_locality():
    async def scenario():
        application = service(SimpleNamespace(latitude=None, longitude=None, city="Tokyo"))
        application.cities.coordinates.return_value = (
            PlaceCoordinates(latitude=35.6762, longitude=139.6503), "Токио"
        )
        result = await application.resolve(request(user_id=uuid4(), device_timezone="UTC"))
        assert result.model_dump() == {
            "timezone": "Asia/Tokyo", "source": "profile_city", "city": "Токио"
        }
        application.cities.coordinates.assert_awaited_once_with("Tokyo")

    asyncio.run(scenario())


def test_unresolved_place_continues_to_profile_coordinates():
    application = service(SimpleNamespace(latitude=55.7558, longitude=37.6173, city="Москва"))
    result = asyncio.run(application.resolve(request(
        place=PlaceCoordinates(latitude=0.0, longitude=-140.0), user_id=uuid4()
    )))
    assert result.timezone == "Europe/Moscow" and result.source == "profile_coordinates"


def test_ocean_coordinates_and_unavailable_profiles_fall_back_to_device():
    async def scenario():
        application = service()
        # timezone_at_land must not label an arbitrary ocean offset as the event place.
        result = await application.resolve(request(
            PlaceCoordinates(latitude=0.0, longitude=-140.0), device_timezone="Asia/Tokyo"
        ))
        assert result.source == "device" and result.timezone == "Asia/Tokyo"
        for error in (UserNotFoundError("missing"), UserInactiveError("inactive")):
            application.users.get_profile.side_effect = error
            result = await application.resolve(request(user_id=uuid4()))
            assert result.source == "device" and result.city is None
        application.users.get_profile.side_effect = None
        application.users.get_profile.return_value = SimpleNamespace(
            latitude=None, longitude=None, city="Unknown city"
        )
        result = await application.resolve(request(user_id=uuid4()))
        assert result.source == "device"

    asyncio.run(scenario())


@pytest.mark.parametrize("place", [
    {"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": -181},
    {"latitude": 0}, {"latitude": "55.7", "longitude": 37.6},
    {"latitude": True, "longitude": 37.6},
    {"latitude": 0, "longitude": 0, "city": "Injected"},
])
def test_coordinate_contract_is_strict_and_paired(place):
    with pytest.raises(ValidationError):
        request(place=place)


@pytest.mark.parametrize("zone", ["", "Not/AZone", "../UTC", "/etc/localtime", 123])
def test_device_timezone_must_be_valid_iana(zone):
    with pytest.raises(ValidationError):
        request(device_timezone=zone)


def test_http_endpoint_validates_and_does_not_cache_personalized_results():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_timezone_service] = lambda: service()
    with TestClient(app) as http:
        response = http.post("/api/maps/timezone", json={
            "place": {"latitude": 35.6762, "longitude": 139.6503},
            "user_id": None, "device_timezone": "Europe/London",
        })
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"timezone": "Asia/Tokyo", "source": "place", "city": None}
        assert http.post("/api/maps/timezone", json={
            "place": None, "user_id": None, "device_timezone": "Invalid/Zone",
        }).status_code == 422


def test_http_timezone_does_not_read_an_unverified_profile():
    app = FastAPI()
    app.include_router(router)
    application = service()
    app.dependency_overrides[get_timezone_service] = lambda: application
    with TestClient(app) as http:
        response = http.post("/api/maps/timezone", json={
            "place": None, "user_id": str(uuid4()), "device_timezone": "UTC",
        })
    assert response.status_code == 403
    application.users.get_profile.assert_not_awaited()


def test_http_timezone_uses_verified_account_when_profile_id_is_null():
    app = FastAPI()
    app.include_router(router)
    viewer = uuid4()
    application = service()
    app.dependency_overrides[get_timezone_service] = lambda: application
    app.dependency_overrides[get_discovery_viewer] = lambda: viewer
    with TestClient(app) as http:
        response = http.post("/api/maps/timezone", json={
            "place": None, "user_id": None, "device_timezone": "UTC",
        })
    assert response.status_code == 200
    assert response.json()["source"] == "device"
    application.users.get_profile.assert_awaited_once_with(viewer)


def test_city_geocoder_reads_locality_without_parsing_address_text(monkeypatch):
    def provider(request, *, timeout):
        assert timeout == 10
        assert "kind=locality" in request.full_url
        return BytesIO(json.dumps({"response": {"GeoObjectCollection": {"featureMember": [{
            "GeoObject": {
                "Point": {"pos": "139.6503 35.6762"},
                "metaDataProperty": {"GeocoderMetaData": {
                    "text": "Arbitrary display text, no usable city here",
                    "Address": {"Components": [{"kind": "locality", "name": "Токио"}]},
                }},
            },
        }]}}}).encode())

    monkeypatch.setattr(yandex_maps_client, "urlopen", provider)
    result = asyncio.run(ProfileCityGeocoder("dummy-secret").coordinates("Tokyo"))
    assert result == (PlaceCoordinates(latitude=35.6762, longitude=139.6503), "Токио")


def test_city_geocoder_does_not_infer_city_from_free_text(monkeypatch):
    def provider(request, *, timeout):
        return BytesIO(json.dumps({"response": {"GeoObjectCollection": {"featureMember": [{
            "GeoObject": {
                "Point": {"pos": "37.6173 55.7558"},
                "metaDataProperty": {"GeocoderMetaData": {
                    "text": "Россия, Москва", "Address": {"Components": []},
                }},
            },
        }]}}}).encode())

    monkeypatch.setattr(yandex_maps_client, "urlopen", provider)
    assert asyncio.run(ProfileCityGeocoder("dummy-secret").coordinates("Москва")) is None


@pytest.mark.parametrize("error_kind", ["permission", "network"])
def test_city_provider_failures_fall_back_without_exposing_keys(monkeypatch, caplog, error_kind):
    def unavailable(request, *, timeout):
        if error_kind == "permission":
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        raise URLError("Request failed: " + request.full_url)

    monkeypatch.setattr(yandex_maps_client, "urlopen", unavailable)

    async def scenario():
        application = service(SimpleNamespace(latitude=None, longitude=None, city="Tokyo"))
        application.cities = ProfileCityGeocoder("dummy-secret")
        result = await application.resolve(request(user_id=uuid4()))
        assert result.source == "device"
        assert "dummy-secret" not in result.model_dump_json()

    asyncio.run(scenario())
    assert "dummy-secret" not in caplog.text
