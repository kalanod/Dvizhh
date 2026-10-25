"""Граница авторизации: действовать можно только от своего имени.

Пока auth-api не выдаёт сессии, backend не знает, кто отправил запрос, и берёт
organizer_id из тела как есть (временный контракт, см. PERSONAL_API.md). Тесты ниже
фиксируют требование заранее и помечены xfail(strict=True): когда авторизация
появится, они начнут проходить, и pytest попросит снять пометку.

Как именно запрос подтверждает пользователя, решит задача авторизации — тогда нужно
заменить ACTING_USER_HEADER на настоящий механизм (cookie сессии или токен).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest

from dvizh_backend.main import app
from dvizh_backend.services.dependencies import get_event_service

ACTING_USER_HEADER = "X-User-Id"
ACTOR_ID = UUID("00000000-0000-0000-0000-0000000000a1")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-0000000000b2")
EVENT_BODY = {
    "title": "Чужой движ",
    "starts_at": "2026-12-01T18:00:00+00:00",
    "format": "ONLINE",
    "online_url": "https://example.com",
}

AWAITING_AUTH = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Нет авторизации: backend доверяет organizer_id из тела запроса",
)


def post_as(actor: UUID, path: str, body: dict) -> tuple[httpx.Response, AsyncMock]:
    """Отправляет запрос от имени actor; сервис подменён, чтобы не нужна была БД."""
    service = MagicMock()
    # Если запрос дошёл до создания события, граница уже нарушена.
    service.create_event = AsyncMock(side_effect=AssertionError("событие создано"))

    async def scenario() -> httpx.Response:
        overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_event_service] = lambda: service
        try:
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                return await http.post(path, json=body, headers={ACTING_USER_HEADER: str(actor)})
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides)

    return asyncio.run(scenario()), service.create_event


@AWAITING_AUTH
@pytest.mark.parametrize("path", ["/api/events", "/api/events/drafts"])
def test_cannot_create_event_on_behalf_of_another_user(path: str) -> None:
    response, create_event = post_as(
        ACTOR_ID, path, {**EVENT_BODY, "organizer_id": str(OTHER_USER_ID)}
    )

    assert response.status_code == 403
    create_event.assert_not_awaited()
