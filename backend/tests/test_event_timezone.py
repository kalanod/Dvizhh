import asyncio
import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dvizh_backend.api.dependencies import get_timezone_service
from dvizh_backend.api.routers.maps import router
from dvizh_backend.api.schemas.timezone import EventTimezoneRequest, PlaceCoordinates
from dvizh_backend.services import yandex_maps_client
from dvizh_backend.services.event_timezone_service import EventTimezoneService
from dvizh_backend.services.place_geocoding import ProfileCityGeocoder


@pytest.mark.parametrize("zone", ["UTC", "Europe/Moscow", "Asia/Tokyo"])
def test_timezone_always_uses_the_browser_zone(zone):
    request = EventTimezoneRequest(
        place=PlaceCoordinates(latitude=35.6762, longitude=139.6503),
        user_id=uuid4(),
        device_timezone=zone,
    )
    response = asyncio.run(EventTimezoneService().resolve(request))
    assert response.model_dump() == {"timezone": zone, "source": "device", "city": None}


@pytest.mark.parametrize("zone", ["", "Not/AZone", "../UTC", "/etc/localtime", 123])
def test_device_zone_is_validated(zone):
    with pytest.raises(ValidationError):
        EventTimezoneRequest(place=None, user_id=None, device_timezone=zone)


def test_compatibility_endpoint_and_unverified_profile_rejection():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_timezone_service] = EventTimezoneService
    with TestClient(app) as http:
        body = {"place": None, "user_id": None, "device_timezone": "Asia/Tokyo"}
        result = http.post("/api/maps/timezone", json=body)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["timezone"] == "Asia/Tokyo"
        assert (
            http.post("/api/maps/timezone", json={**body, "user_id": str(uuid4())}).status_code
            == 403
        )


def test_city_geocoder_reads_locality_without_parsing_address_text(monkeypatch):
    def provider(request, *, timeout):
        assert timeout == 10
        assert "kind=locality" in request.full_url
        return BytesIO(
            json.dumps(
                {
                    "response": {
                        "GeoObjectCollection": {
                            "featureMember": [
                                {
                                    "GeoObject": {
                                        "Point": {"pos": "139.6503 35.6762"},
                                        "metaDataProperty": {
                                            "GeocoderMetaData": {
                                                "text": "Display text without city",
                                                "Address": {
                                                    "Components": [
                                                        {"kind": "locality", "name": "Токио"}
                                                    ]
                                                },
                                            }
                                        },
                                    },
                                }
                            ]
                        }
                    }
                }
            ).encode()
        )

    monkeypatch.setattr(yandex_maps_client, "urlopen", provider)
    result = asyncio.run(ProfileCityGeocoder("dummy-secret").coordinates("Tokyo"))
    assert result == (PlaceCoordinates(latitude=35.6762, longitude=139.6503), "Токио")


def test_city_geocoder_does_not_infer_city_from_free_text(monkeypatch):
    def provider(request, *, timeout):
        return BytesIO(
            json.dumps(
                {
                    "response": {
                        "GeoObjectCollection": {
                            "featureMember": [
                                {
                                    "GeoObject": {
                                        "Point": {"pos": "37.6173 55.7558"},
                                        "metaDataProperty": {
                                            "GeocoderMetaData": {
                                                "text": "Россия, Москва",
                                                "Address": {"Components": []},
                                            }
                                        },
                                    },
                                }
                            ]
                        }
                    }
                }
            ).encode()
        )

    monkeypatch.setattr(yandex_maps_client, "urlopen", provider)
    assert asyncio.run(ProfileCityGeocoder("dummy-secret").coordinates("Москва")) is None


@pytest.mark.parametrize("error_kind", ["permission", "network"])
def test_city_provider_failure_does_not_expose_keys(monkeypatch, caplog, error_kind):
    def unavailable(request, *, timeout):
        if error_kind == "permission":
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        raise URLError("Request failed: " + request.full_url)

    monkeypatch.setattr(yandex_maps_client, "urlopen", unavailable)
    assert asyncio.run(ProfileCityGeocoder("dummy-secret").coordinates("Tokyo")) is None
    assert "dummy-secret" not in caplog.text
