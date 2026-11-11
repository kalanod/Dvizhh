import asyncio
import json
import logging
import re
from typing import Annotated, Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..services.dependencies import SettingsDep

router = APIRouter(prefix="/api/maps", tags=["maps"])
logger = logging.getLogger("uvicorn.error")


def _redact(message: str, *keys: str) -> str:
    for key in keys:
        if key:
            message = message.replace(key, "[REDACTED]")
    return re.sub(r"(?i)(apikey|api_key|key)=([^\s&#\"']+)", r"\1=[REDACTED]", message)[:2000]


class MapClientError(BaseModel):
    stage: Literal["script_load", "sdk_missing", "sdk_ready", "map_init", "marker_update"]
    message: str = Field(max_length=2000)
    online: bool | None = None


@router.post("/client-error", status_code=204, summary="Ошибка карты из браузера в логи backend.")
async def client_error(body: MapClientError, request: Request, settings: SettingsDep) -> Response:
    logger.error(
        "Yandex Maps browser error: stage=%s origin=%s online=%s message=%r",
        body.stage,
        urlsplit(request.headers.get("origin", request.headers.get("referer", ""))).netloc,
        body.online,
        _redact(
            body.message,
            settings.yandex_maps_api_key,
            settings.yandex_suggest_api_key,
            settings.yandex_geocoder_api_key,
            settings.yandex_search_api_key,
        ),
    )
    return Response(status_code=204)


def _fetch_json(url: str, params: dict[str, str], referer: str) -> Any:
    request = UrlRequest(f"{url}?{urlencode(params)}", headers={"Referer": referer})
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace") if exc.fp else ""
        logger.warning(
            "Yandex Maps API error: service=%s status=%s referer_host=%s response=%r",
            urlsplit(url).netloc,
            exc.code,
            urlsplit(referer).netloc,
            _redact(detail, params.get("apikey", "")),
        )
        if exc.code in (401, 403):
            if urlsplit(url).netloc == "search-maps.yandex.ru":
                message = (
                    "Яндекс отклонил доступ к API Поиска по организациям. "
                    "Подсказки доступны, но получить точку выбранного заведения пока нельзя."
                )
            else:
                message = (
                    "Яндекс отклонил ключ API. Проверьте подключённые продукты и ограничения ключа."
                )
        elif exc.code == 429:
            message = "Исчерпан лимит запросов Яндекс Карт. Попробуйте позже."
        else:
            message = "Поиск Яндекс Карт временно недоступен. Попробуйте ещё раз."
        raise HTTPException(503, message) from None
    except (URLError, TimeoutError, ValueError) as exc:
        logger.warning(
            "Yandex Maps request failed: service=%s error_type=%s detail=%r",
            urlsplit(url).netloc,
            type(exc).__name__,
            _redact(str(exc), params.get("apikey", "")),
        )
        raise HTTPException(503, "Не удалось получить ответ Яндекс Карт.") from None


@router.get("/config", summary="Ключ для отображения Яндекс Карт в браузере.")
async def maps_config(settings: SettingsDep, response: Response) -> dict[str, str | bool]:
    logger.info(
        "Yandex Maps config: map_key_present=%s suggest_key_present=%s geocoder_key_present=%s",
        bool(settings.yandex_maps_api_key),
        bool(settings.yandex_suggest_api_key),
        bool(settings.yandex_geocoder_api_key or settings.yandex_maps_api_key),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "api_key": settings.yandex_maps_api_key,
        "search_enabled": bool(
            settings.yandex_suggest_api_key
            and (settings.yandex_geocoder_api_key or settings.yandex_maps_api_key)
        ),
    }


@router.get("/suggest", summary="Подсказки адресов и заведений Яндекса.")
async def suggest(
    request: Request,
    response: Response,
    settings: SettingsDep,
    text: Annotated[str, Query(min_length=3, max_length=500)],
    city: Annotated[str, Query(max_length=120)] = "",
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> list[dict[str, str | None]]:
    if not settings.yandex_suggest_api_key:
        raise HTTPException(503, "Поиск адресов пока не настроен.")
    response.headers["Cache-Control"] = "no-store"
    data = await asyncio.to_thread(
        _fetch_json,
        "https://suggest-maps.yandex.ru/v1/suggest",
        {
            "apikey": settings.yandex_suggest_api_key,
            "text": f"{city}, {text}" if city.strip() and latitude is None else text,
            "lang": "ru_RU",
            "types": "geo,biz",
            "results": "5",
            "print_address": "1",
            "attrs": "uri",
            **(
                {"ll": f"{longitude},{latitude}", "spn": "0.1,0.1", "strict_bounds": "0"}
                if latitude is not None and longitude is not None
                else {}
            ),
        },
        request.headers.get("referer", str(request.base_url)),
    )
    return [
        {
            "title": item["title"]["text"],
            "subtitle": item.get("subtitle", {}).get("text", ""),
            "uri": item.get("uri", ""),
            "kind": "biz" if urlsplit(item.get("uri", "")).netloc == "org" else "geo",
            "city": next(
                (
                    part["name"]
                    for part in item.get("address", {}).get("component", [])
                    if "LOCALITY" in part.get("kind", [])
                ),
                None,
            ),
            "address": item.get("address", {}).get("formatted_address", item["title"]["text"]),
        }
        for item in data.get("results", [])
    ]


@router.get("/geocode", summary="Определить место по адресу, подсказке или координатам.")
async def geocode(
    request: Request,
    response: Response,
    settings: SettingsDep,
    query: Annotated[str, Query(max_length=500)] = "",
    uri: Annotated[str, Query(max_length=4000)] = "",
) -> dict[str, str | None]:
    key = settings.yandex_geocoder_api_key or settings.yandex_maps_api_key
    if not key:
        raise HTTPException(503, "Поиск адресов пока не настроен.")
    if not query.strip() and not uri:
        raise HTTPException(422, "Укажите адрес или точку на карте.")
    response.headers["Cache-Control"] = "no-store"
    if urlsplit(uri).netloc == "org":
        key_source = (
            "YANDEX_SEARCH_API_KEY"
            if settings.yandex_search_api_key
            else "YANDEX_GEOCODER_API_KEY"
            if settings.yandex_geocoder_api_key
            else "YANDEX_MAPS_API_KEY"
        )
        logger.info("Yandex organization lookup: key_source=%s", key_source)
        data = await asyncio.to_thread(
            _fetch_json,
            "https://search-maps.yandex.ru/v1/",
            {
                "apikey": settings.yandex_search_api_key or key,
                "lang": "ru_RU",
                "uri": uri,
                "results": "1",
                "type": "biz",
            },
            request.headers.get("referer", str(request.base_url)),
        )
        features = data.get("features", [])
        if not features:
            raise HTTPException(404, "Заведение не найдено. Выберите другой вариант.")
        place = features[0]
        longitude, latitude = place["geometry"]["coordinates"]
        company = place["properties"].get("CompanyMetaData", {})
        return {
            "name": company.get("name", place["properties"].get("name")),
            "address_line": company.get("address", place["properties"].get("description", "")),
            "city": None,
            "latitude": str(latitude),
            "longitude": str(longitude),
        }
    data = await asyncio.to_thread(
        _fetch_json,
        "https://geocode-maps.yandex.ru/v1/",
        {
            "apikey": key,
            "lang": "ru_RU",
            "format": "json",
            "results": "1",
            **({"uri": uri} if uri else {"geocode": query}),
        },
        request.headers.get("referer", str(request.base_url)),
    )
    members = data["response"]["GeoObjectCollection"]["featureMember"]
    if not members:
        raise HTTPException(404, "Адрес не найден. Уточните его или выберите точку на карте.")
    place = members[0]["GeoObject"]
    longitude, latitude = place["Point"]["pos"].split()
    metadata = place["metaDataProperty"]["GeocoderMetaData"]
    address = metadata.get("Address", {})
    city = next(
        (part["name"] for part in address.get("Components", []) if part["kind"] == "locality"),
        None,
    )
    return {
        "address_line": metadata["text"],
        "city": city,
        "latitude": latitude,
        "longitude": longitude,
    }
