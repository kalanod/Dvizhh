import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dvizh_backend.api import security
from dvizh_backend.api.dependencies import get_admin_user_service
from dvizh_backend.api.errors import register_error_handlers
from dvizh_backend.api.routers.admin import router
from dvizh_backend.api.schemas.admin_user import AdminUserDTO, AdminUserPage, ResetPasswordCommand
from dvizh_backend.services.account_context import AccountRequestContext
from dvizh_backend.services.account_gateway import AccountCommandError, AccountGateway


def test_admin_user_routes_keep_authorization_and_redact_invalid_passwords(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    user = AdminUserDTO(id=uuid4(), username="member", email=None, role="user")
    service = SimpleNamespace(
        search=AsyncMock(return_value=AdminUserPage(
            items=[user], offset=0, limit=20, has_more=False,
        )),
        change_role=AsyncMock(return_value=user), reset_password=AsyncMock(),
    )
    app.dependency_overrides[get_admin_user_service] = lambda: service
    monkeypatch.setattr(
        security, "fetch_current_account",
        lambda *_: security.AdminAccount(id=uuid4(), role="admin"),
    )
    headers = {"X-Dvizh-Admin": "1", "Origin": "http://testserver"}
    path = f"/api/admin/users/{user.id}/password"
    with TestClient(app) as client:
        assert client.get("/api/admin/users").status_code == 401
        client.cookies.set("dvizh_access", "admin-session")
        response = client.get("/api/admin/users", params={"q": "member", "offset": 20, "limit": 10})
        assert response.status_code == 200 and response.json()["items"][0]["username"] == "member"
        assert response.headers["cache-control"] == "no-store"
        assert service.search.call_args.args[:3] == ("member", 20, 10)
        assert client.get("/api/admin/users", params={"limit": 101}).status_code == 422
        assert client.post(path, json={"new_password": "admin-reset-password"}).status_code == 403
        assert client.post(path, json={"new_password": "admin-reset-password"}, headers={
            **headers, "Origin": "https://evil.example",
        }).status_code == 403
        service.reset_password.assert_not_awaited()
        for body in ({"new_password": "short"}, {"new_password": "x" * 129},
                     {"new_password": "admin-reset-password", "extra": "secret-extra"}):
            response = client.post(path, json=body, headers=headers)
            assert response.status_code == 422
            assert "short" not in response.text and "admin-reset-password" not in response.text
            assert "secret-extra" not in response.text
        response = client.post(path, json={"new_password": "admin-reset-password"}, headers=headers)
        assert response.status_code == 204 and not response.content
        command = service.reset_password.call_args.args[1]
        assert command.new_password.get_secret_value() == "admin-reset-password"
        assert "admin-reset-password" not in repr(command)
        monkeypatch.setattr(
            security, "fetch_current_account",
            lambda *_: security.AdminAccount(id=uuid4(), role="user"),
        )
        assert client.get("/api/admin/users").status_code == 403
        assert client.post(
            path, json={"new_password": "admin-reset-password"}, headers=headers,
        ).status_code == 403


def test_admin_gateway_preserves_credentials_and_never_relays_upstream_password_errors(monkeypatch):
    from dvizh_backend.services import account_gateway

    gateway = AccountGateway("http://auth-api:8003")
    context = AccountRequestContext("opaque-token", "dvizzh.space", "https://dvizzh.space", "")
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.status = 204
    response.read.return_value = b""
    monkeypatch.setattr(account_gateway, "build_opener", lambda *_: opener)
    user_id = uuid4()
    command = ResetPasswordCommand(new_password=" new-admin-password ")
    asyncio.run(gateway.reset_password(user_id, command, context))
    request = opener.open.call_args.args[0]
    assert request.full_url == f"http://auth-api:8003/api/auth/admin/users/{user_id}/password"
    assert request.get_method() == "POST"
    assert request.get_header("X-dvizh-admin") == "1"
    assert request.get_header("Cookie") == "dvizh_access=opaque-token"
    assert request.get_header("Origin") == "https://dvizzh.space"
    assert request.get_header("Host") == "dvizzh.space"
    assert json.loads(request.data) == {"new_password": " new-admin-password "}
    for status, expected in (
        (401, 401), (403, 403), (404, 404), (409, 409), (422, 422), (500, 503),
    ):
        opener.open.side_effect = HTTPError(
            request.full_url, status, "error", {}, io.BytesIO(b'{"detail":"new-admin-password"}'),
        )
        with pytest.raises(AccountCommandError) as error:
            asyncio.run(gateway.reset_password(user_id, command, context))
        assert error.value.status_code == expected
        assert "new-admin-password" not in str(error.value)


def test_admin_gateway_search_is_encoded_and_validates_response(monkeypatch):
    from dvizh_backend.services import account_gateway

    gateway = AccountGateway("http://auth-api:8003")
    context = AccountRequestContext("opaque-token", "dvizzh.space", None, "")
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.status = 200
    response.read.return_value = json.dumps({
        "items": [], "offset": 0, "limit": 20, "has_more": False,
    }).encode()
    monkeypatch.setattr(account_gateway, "build_opener", lambda *_: opener)
    assert not asyncio.run(gateway.search_users("a&b", 0, 20, context)).items
    assert "q=a%26b&offset=0&limit=20" in opener.open.call_args.args[0].full_url
    response.read.return_value = b'{"items":[{"password_hash":"secret"}]}'
    with pytest.raises(AccountCommandError) as error:
        asyncio.run(gateway.search_users("", 0, 20, context))
    assert error.value.status_code == 503
