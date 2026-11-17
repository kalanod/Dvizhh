from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dvizh_backend.api.dependencies import get_user_service
from dvizh_backend.api.routers import friends, personal


def test_pair_route_does_not_shadow_the_friend_request_list() -> None:
    app = FastAPI()
    app.include_router(friends.router)
    app.include_router(personal.router)
    users = SimpleNamespace(
        get_friendship=AsyncMock(return_value=None),
        list_friendship_requests=AsyncMock(return_value=[]),
    )
    app.dependency_overrides[get_user_service] = lambda: users
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")
    with TestClient(app) as client:
        response = client.get(f"/api/users/{first}/friends/{second}")
        assert response.status_code == 200
        assert response.json() is None
        users.get_friendship.assert_awaited_once_with(first, second)
        response = client.get(f"/api/users/{first}/friends/requests?direction=outgoing")
        assert response.status_code == 200
        assert response.json() == []
        users.list_friendship_requests.assert_awaited_once_with(
            first, incoming=False, offset=0, limit=20,
        )
