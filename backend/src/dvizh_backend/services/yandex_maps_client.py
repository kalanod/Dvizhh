"""Yandex HTTP transport; credentials and provider failures never leak to API responses."""

import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from .maps_errors import MapsUnavailableError

logger = logging.getLogger("uvicorn.error")


def redact(message: str, *keys: str) -> str:
    for key in keys:
        if key:
            message = message.replace(key, "[REDACTED]")
    return re.sub(r"(?i)(apikey|api_key|key)=([^\s&#\"']+)", r"\1=[REDACTED]", message)[:2000]


class YandexMapsClient:
    def fetch_json(self, url: str, params: dict[str, str], referer: str) -> Any:
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
                        "Яндекс отклонил ключ API. "
                        "Проверьте подключённые продукты и ограничения ключа."
                    )
            elif exc.code == 429:
                message = "Исчерпан лимит запросов Яндекс Карт. Попробуйте позже."
            else:
                message = "Поиск Яндекс Карт временно недоступен. Попробуйте ещё раз."
            raise MapsUnavailableError(message) from None
        except (URLError, TimeoutError, ValueError) as exc:
            logger.warning(
                "Yandex Maps request failed: service=%s error_type=%s detail=%r",
                urlsplit(url).netloc,
                type(exc).__name__,
                redact(str(exc), params.get("apikey", "")),
            )
            raise MapsUnavailableError("Не удалось получить ответ Яндекс Карт.") from None
