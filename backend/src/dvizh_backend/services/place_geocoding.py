"""Yandex transport shared by map HTTP endpoints and application services."""

import asyncio
import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from ..dto.timezone import PlaceCoordinates

logger = logging.getLogger("uvicorn.error")


class PlaceProviderUnavailable(Exception):
    pass


class ProfileCityGeocoder:
    def __init__(self, api_key: str, referer: str = "") -> None:
        self.api_key = api_key
        self.referer = referer

    async def coordinates(self, city: str) -> tuple[PlaceCoordinates, str] | None:
        if not self.api_key:
            return None
        try:
            data = await asyncio.to_thread(
                fetch_json,
                "https://geocode-maps.yandex.ru/v1/",
                {"apikey": self.api_key, "lang": "ru_RU", "format": "json", "results": "1",
                 "geocode": city, "kind": "locality"},
                self.referer,
            )
            members = data["response"]["GeoObjectCollection"]["featureMember"]
            if not members:
                return None
            place = members[0]["GeoObject"]
            metadata = place["metaDataProperty"]["GeocoderMetaData"]
            locality = next((
                component["name"] for component in metadata.get("Address", {}).get("Components", [])
                if component.get("kind") == "locality"
            ), None)
            if not locality:
                return None
            longitude, latitude = place["Point"]["pos"].split()
            return PlaceCoordinates(latitude=float(latitude), longitude=float(longitude)), locality
        except (PlaceProviderUnavailable, KeyError, TypeError, ValueError, AttributeError, OSError):
            return None


def redact(message: str, *keys: str) -> str:
    for key in keys:
        if key:
            message = message.replace(key, "[REDACTED]")
    return re.sub(r"(?i)(apikey|api_key|key)=([^\s&#\"']+)", r"\1=[REDACTED]", message)[:2000]



def fetch_json(
    url: str, params: dict[str, str], referer: str, *, opener=None
) -> Any:
    request = UrlRequest(f"{url}?{urlencode(params)}", headers={"Referer": referer})
    try:
        with (opener or urlopen)(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace") if exc.fp else ""
        logger.warning(
            "Yandex Maps API error: service=%s status=%s referer_host=%s response=%r",
            urlsplit(url).netloc,
            exc.code,
            urlsplit(referer).netloc,
            redact(detail, params.get("apikey", "")),
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
        raise PlaceProviderUnavailable(message) from None
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning(
            "Yandex Maps request failed: service=%s error_type=%s detail=%r",
            urlsplit(url).netloc,
            type(exc).__name__,
            redact(str(exc), params.get("apikey", "")),
        )
        raise PlaceProviderUnavailable("Не удалось получить ответ Яндекс Карт.") from None

