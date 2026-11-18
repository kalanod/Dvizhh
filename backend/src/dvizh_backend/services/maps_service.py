"""Place lookup use cases and mapping of provider data to the application contract."""

import asyncio
import logging
from urllib.parse import urlsplit

from dvizh_backend.config import Settings

from .maps_errors import InvalidPlaceQueryError, MapsUnavailableError, PlaceNotFoundError
from .yandex_maps_client import YandexMapsClient

logger = logging.getLogger(__name__)


class MapsService:
    def __init__(self, settings: Settings, client: YandexMapsClient | None = None) -> None:
        self.settings = settings
        self.client = client or YandexMapsClient()

    def configuration(self) -> dict[str, str | bool]:
        settings = self.settings
        return {
            "api_key": settings.yandex_maps_api_key,
            "search_enabled": bool(
                settings.yandex_suggest_api_key
                and (settings.yandex_geocoder_api_key or settings.yandex_maps_api_key)
            ),
        }

    def report_client_error(self, *, stage: str, online: bool | None) -> None:
        logger.error("Yandex Maps browser error", extra={"stage": stage, "online": online})

    async def suggest(
        self, text: str, city: str, latitude: float | None, longitude: float | None,
        referer: str,
    ) -> list[dict[str, str | None]]:
        settings = self.settings
        if not settings.yandex_suggest_api_key:
            raise MapsUnavailableError("Поиск адресов пока не настроен.")
        data = await asyncio.to_thread(
            self.client.fetch_json,
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
            referer,
            operation="suggest",
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

    async def geocode(self, query: str, uri: str, referer: str) -> dict[str, str | None]:
        settings = self.settings
        key = settings.yandex_geocoder_api_key or settings.yandex_maps_api_key
        if not key:
            raise MapsUnavailableError("Поиск адресов пока не настроен.")
        if not query.strip() and not uri:
            raise InvalidPlaceQueryError("Укажите адрес или точку на карте.")
        if urlsplit(uri).netloc == "org":
            key_source = (
                "YANDEX_SEARCH_API_KEY"
                if settings.yandex_search_api_key
                else "YANDEX_GEOCODER_API_KEY"
                if settings.yandex_geocoder_api_key
                else "YANDEX_MAPS_API_KEY"
            )
            logger.info("Yandex organization lookup", extra={"key_source": key_source})
            data = await asyncio.to_thread(
                self.client.fetch_json,
                "https://search-maps.yandex.ru/v1/",
                {
                    "apikey": settings.yandex_search_api_key or key,
                    "lang": "ru_RU",
                    "uri": uri,
                    "results": "1",
                    "type": "biz",
                },
                referer,
                operation="search_organization",
            )
            features = data.get("features", [])
            if not features:
                raise PlaceNotFoundError("Заведение не найдено. Выберите другой вариант.")
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
            self.client.fetch_json,
            "https://geocode-maps.yandex.ru/v1/",
            {
                "apikey": key,
                "lang": "ru_RU",
                "format": "json",
                "results": "1",
                **({"uri": uri} if uri else {"geocode": query}),
            },
            referer,
            operation="geocode",
        )
        members = data["response"]["GeoObjectCollection"]["featureMember"]
        if not members:
            raise PlaceNotFoundError("Адрес не найден. Уточните его или выберите точку на карте.")
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
