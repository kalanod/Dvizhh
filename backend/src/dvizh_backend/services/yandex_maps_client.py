"""Yandex HTTP transport; credentials and provider failures never leak to API responses."""

import json
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from dvizh_logging import record_dependency

from .maps_errors import MapsUnavailableError


class YandexMapsClient:
    def fetch_json(
        self, url: str, params: dict[str, str], referer: str, *, operation: str
    ) -> Any:
        request = UrlRequest(f"{url}?{urlencode(params)}", headers={"Referer": referer})
        upstream = urlsplit(url).netloc
        upstream_status = None
        started = perf_counter()
        try:
            with urlopen(request, timeout=10) as response:
                upstream_status = getattr(response, "status", None)
                data = json.load(response)
        except HTTPError as exc:
            exc.close()
            record_dependency(
                "yandex_maps",
                operation,
                started,
                error=exc,
                upstream=upstream,
                upstream_status=exc.code,
            )
            if exc.code in (401, 403):
                if upstream == "search-maps.yandex.ru":
                    message = (
                        "Яндекс отклонил доступ к API Поиска по организациям. "
                        "Подсказки доступны, но получить точку выбранного заведения пока нельзя."
                    )
                else:
                    message = (
                        "Яндекс отклонил ключ API. "
                        "Проверьте подключённые продукты и ограничения ключа."
                    )
            elif exc.code == 429:
                message = "Исчерпан лимит запросов Яндекс Карт. Попробуйте позже."
            else:
                message = "Поиск Яндекс Карт временно недоступен. Попробуйте ещё раз."
            raise MapsUnavailableError(message) from None
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            record_dependency(
                "yandex_maps",
                operation,
                started,
                error=exc,
                upstream=upstream,
                upstream_status=upstream_status,
            )
            raise MapsUnavailableError("Не удалось получить ответ Яндекс Карт.") from None
        record_dependency(
            "yandex_maps", operation, started, upstream=upstream, upstream_status=upstream_status
        )
        return data
