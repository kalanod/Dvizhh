"""Structured profile-city lookup using the shared Yandex transport."""

import asyncio

from dvizh_backend.api.schemas.timezone import PlaceCoordinates

from .maps_errors import MapsUnavailableError
from .yandex_maps_client import YandexMapsClient


class ProfileCityGeocoder:
    def __init__(
        self, api_key: str, referer: str = "", client: YandexMapsClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.referer = referer
        self.client = client or YandexMapsClient()

    async def coordinates(self, city: str) -> tuple[PlaceCoordinates, str] | None:
        if not self.api_key:
            return None
        try:
            data = await asyncio.to_thread(
                self.client.fetch_json,
                "https://geocode-maps.yandex.ru/v1/",
                {
                    "apikey": self.api_key, "lang": "ru_RU", "format": "json", "results": "1",
                    "geocode": city, "kind": "locality",
                },
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
        except (MapsUnavailableError, KeyError, TypeError, ValueError, AttributeError, OSError):
            return None
