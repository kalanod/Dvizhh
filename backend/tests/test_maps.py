import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest
from dvizh_logging import JsonFormatter
from dvizh_logging.http import RequestLoggingMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.routers import maps


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(maps.router)
    settings = Settings(
        _env_file=None,
        yandex_maps_api_key="browser-key",
        yandex_suggest_api_key="suggest-secret",
        yandex_geocoder_api_key="geocoder-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must not call Yandex")

    monkeypatch.setattr(maps, "urlopen", no_network)
    with TestClient(RequestLoggingMiddleware(app)) as client:
        yield client, settings


def provider(monkeypatch, data):
    requests = []

    def respond(request, *, timeout):
        requests.append(request)
        assert timeout == 10
        return BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(maps, "urlopen", respond)
    return requests


def test_config_exposes_only_browser_key(client):
    http, settings = client
    response = http.get("/api/maps/config")
    assert response.json() == {"api_key": "browser-key", "search_enabled": True}
    assert "secret" not in response.text
    assert response.headers["cache-control"] == "no-store"
    settings.yandex_suggest_api_key = ""
    assert http.get("/api/maps/config").json()["search_enabled"] is False
    assert http.get("/api/maps/suggest", params={"text": "Невский"}).status_code == 503


def test_suggestions_keep_order_and_uri(client, monkeypatch):
    http, _ = client
    requests = provider(
        monkeypatch,
        {
            "results": [
                {
                    "title": {"text": "Невский, 1"},
                    "subtitle": {"text": "Санкт-Петербург"},
                    "address": {"formatted_address": "Россия, Санкт-Петербург, Невский, 1"},
                    "uri": "ymapsbm1://geo?data=one",
                },
                {"title": {"text": "Невский проспект"}, "uri": "ymapsbm1://geo?data=two"},
            ],
        },
    )
    response = http.get(
        "/api/maps/suggest",
        params={"text": "Невский", "city": "СПб"},
        headers={"Referer": "http://localhost:8080/events/new"},
    )
    assert response.status_code == 200
    assert [item["uri"] for item in response.json()] == [
        "ymapsbm1://geo?data=one",
        "ymapsbm1://geo?data=two",
    ]
    params = parse_qs(urlparse(requests[0].full_url).query)
    assert params["text"] == ["СПб, Невский"]
    assert params["attrs"] == ["uri"]
    assert params["types"] == ["geo,biz"]
    assert params["apikey"] == ["suggest-secret"]
    assert requests[0].get_header("Referer") == "http://localhost:8080/events/new"
    assert response.headers["cache-control"] == "no-store"


def test_nearby_search_bias_does_not_exclude_other_areas(client, monkeypatch):
    http, _ = client
    requests = provider(monkeypatch, {"results": []})
    response = http.get(
        "/api/maps/suggest",
        params={
            "text": "антикафе",
            "city": "Другой город",
            "latitude": 59.93,
            "longitude": 30.31,
        },
    )
    assert response.status_code == 200
    params = parse_qs(urlparse(requests[0].full_url).query)
    assert params["text"] == ["антикафе"]
    assert params["ll"] == ["30.31,59.93"]
    assert params["spn"] == ["0.1,0.1"]
    assert params["strict_bounds"] == ["0"]


def test_business_suggestion_resolves_exact_organization_not_its_street(client, monkeypatch):
    http, settings = client
    settings.yandex_search_api_key = "search-secret"
    requests = provider(
        monkeypatch,
        {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [30.31, 59.93]},
                    "properties": {
                        "CompanyMetaData": {
                            "name": "Антикафе",
                            "address": "Санкт-Петербург, Невский, 1",
                        }
                    },
                }
            ]
        },
    )
    response = http.get("/api/maps/geocode", params={"uri": "ymapsbm1://org?oid=123"})
    assert response.status_code == 200
    assert response.json()["name"] == "Антикафе"
    assert response.json()["longitude"] == "30.31"
    assert response.json()["latitude"] == "59.93"
    assert urlparse(requests[0].full_url).netloc == "search-maps.yandex.ru"
    params = parse_qs(urlparse(requests[0].full_url).query)
    assert params["uri"] == ["ymapsbm1://org?oid=123"]
    assert params["apikey"] == ["search-secret"]
    assert "geocode" not in params


def test_business_name_and_city_are_available_in_suggestions(client, monkeypatch):
    http, _ = client
    provider(
        monkeypatch,
        {
            "results": [
                {
                    "title": {"text": "Антикафе"},
                    "uri": "ymapsbm1://org?oid=123",
                    "address": {
                        "formatted_address": "Невский, 1",
                        "component": [
                            {"kind": ["LOCALITY"], "name": "Санкт-Петербург"},
                        ],
                    },
                }
            ]
        },
    )
    result = http.get("/api/maps/suggest", params={"text": "антикафе"}).json()[0]
    assert result["kind"] == "biz"
    assert result["city"] == "Санкт-Петербург"


def test_business_permission_error_identifies_product_and_key_source(client, monkeypatch, caplog):
    http, settings = client
    settings.yandex_search_api_key = "organization-secret"

    def denied(request, *, timeout):
        assert parse_qs(urlparse(request.full_url).query)["apikey"] == ["organization-secret"]
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(maps, "urlopen", denied)
    with caplog.at_level("INFO", logger=maps.__name__):
        response = http.get("/api/maps/geocode", params={"uri": "ymapsbm1://org?oid=123"})
    assert response.status_code == 503
    assert "API Поиска по организациям" in response.json()["detail"]
    assert any(
        getattr(record, "key_source", "") == "YANDEX_SEARCH_API_KEY" for record in caplog.records
    )
    assert "organization-secret" not in caplog.text


def test_business_without_separate_key_uses_geocoder_key(client, monkeypatch, caplog):
    http, _ = client
    requests = provider(monkeypatch, {"features": []})
    with caplog.at_level("INFO", logger=maps.__name__):
        response = http.get("/api/maps/geocode", params={"uri": "ymapsbm1://org?oid=123"})
    assert response.status_code == 404
    assert parse_qs(urlparse(requests[0].full_url).query)["apikey"] == ["geocoder-secret"]
    assert any(
        getattr(record, "key_source", "") == "YANDEX_GEOCODER_API_KEY" for record in caplog.records
    )


PLACE = {
    "response": {
        "GeoObjectCollection": {
            "featureMember": [
                {
                    "GeoObject": {
                        "Point": {"pos": "30.315868 59.939095"},
                        "metaDataProperty": {
                            "GeocoderMetaData": {
                                "text": "Россия, Санкт-Петербург, Невский проспект, 1",
                                "Address": {
                                    "Components": [
                                        {"kind": "country", "name": "Россия"},
                                        {"kind": "locality", "name": "Санкт-Петербург"},
                                    ]
                                },
                            }
                        },
                    }
                }
            ]
        }
    },
}


def test_geocode_resolves_selected_uri_and_preserves_coordinate_order(client, monkeypatch):
    http, _ = client
    requests = provider(monkeypatch, PLACE)
    response = http.get(
        "/api/maps/geocode",
        params={
            "uri": "ymapsbm1://geo?data=one",
            "query": "ignored free text",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "latitude": "59.939095",
        "longitude": "30.315868",
        "city": "Санкт-Петербург",
        "address_line": "Россия, Санкт-Петербург, Невский проспект, 1",
    }
    params = parse_qs(urlparse(requests[0].full_url).query)
    assert params["uri"] == ["ymapsbm1://geo?data=one"]
    assert "geocode" not in params
    assert params["apikey"] == ["geocoder-secret"]


def test_reverse_geocode_and_shared_map_key(client, monkeypatch):
    http, settings = client
    settings.yandex_geocoder_api_key = ""
    requests = provider(monkeypatch, PLACE)
    response = http.get("/api/maps/geocode", params={"query": "30.315868,59.939095"})
    assert response.status_code == 200
    params = parse_qs(urlparse(requests[0].full_url).query)
    assert params["geocode"] == ["30.315868,59.939095"]
    assert params["apikey"] == ["browser-key"]


def test_geocode_not_found(client, monkeypatch):
    http, _ = client
    provider(monkeypatch, {"response": {"GeoObjectCollection": {"featureMember": []}}})
    assert http.get("/api/maps/geocode", params={"query": "missing"}).status_code == 404


@pytest.mark.parametrize("status", [403, 429])
def test_provider_error_correlates_without_leaking_url(client, monkeypatch, caplog, status):
    http, _ = client

    def error(request, *, timeout):
        raise HTTPError(request.full_url, status, "provider error", {}, None)

    monkeypatch.setattr(maps, "urlopen", error)
    monkeypatch.setattr(caplog.handler, "formatter", JsonFormatter("backend"))
    response = http.get("/api/maps/geocode", params={"query": "Москва"})
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "apikey" not in response.text
    records = [json.loads(line) for line in caplog.text.splitlines()]
    provider_log = next(record for record in records if record.get("dependency") == "yandex_maps")
    assert provider_log["request_id"] == response.headers["X-Request-ID"]
    assert provider_log["operation"] == "geocode"
    assert provider_log["status"] == "ERROR"
    assert provider_log["upstream_status"] == status
    assert provider_log["error_type"] == "HTTPError"
    assert "geocoder-secret" not in caplog.text
    assert "apikey" not in caplog.text


def test_browser_error_reaches_server_log_without_keys(client, caplog):
    http, _ = client
    response = http.post(
        "/api/maps/client-error",
        json={
            "stage": "sdk_ready",
            "online": True,
            "message": "Failed: apikey=browser-key&key=suggest-secret geocoder-secret",
        },
        headers={"Origin": "http://localhost:8080"},
    )
    assert response.status_code == 204
    record = next(record for record in caplog.records if record.name == maps.__name__)
    assert record.stage == "sdk_ready"
    assert record.online is True
    for secret in ("browser-key", "suggest-secret", "geocoder-secret", "localhost:8080"):
        assert secret not in str(vars(record))
