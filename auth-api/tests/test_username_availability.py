from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dvizh_auth.api.dependencies import get_session
from dvizh_auth.api.routers.auth import router


def test_username_availability_validates_and_returns_no_account_data() -> None:
    app = FastAPI()
    app.include_router(router)
    session = SimpleNamespace(scalar=AsyncMock(return_value=False))
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get("/api/auth/username-availability", params={"username": " MEMBER "})
        assert response.status_code == 200
        assert response.json() == {"username": "member", "available": True}
        assert response.headers["cache-control"] == "no-store"
        assert "EXISTS" in str(session.scalar.call_args.args[0])
        assert "password_hash" not in str(session.scalar.call_args.args[0])
        session.scalar.return_value = True
        response = client.get("/api/auth/username-availability", params={"username": "member"})
        assert response.json() == {"username": "member", "available": False}
        session.scalar.reset_mock()
        for username in ("ab", "invalid-name", "a" * 51):
            assert client.get(
                "/api/auth/username-availability", params={"username": username},
            ).status_code == 422
        session.scalar.assert_not_awaited()
