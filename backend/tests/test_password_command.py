import asyncio
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

import httpx
import pytest

from dvizh_backend.api.dependencies import get_user_service
from dvizh_backend.api.schemas.account import ChangePasswordCommand
from dvizh_backend.main import app
from dvizh_backend.services.account_context import AccountRequestContext
from dvizh_backend.services.account_gateway import AccountCommandError, AccountGateway
from dvizh_backend.services.user_service import UserService


def test_user_service_only_delegates_password_command() -> None:
    gateway = MagicMock(change_password=AsyncMock())
    database = AsyncMock()
    command = ChangePasswordCommand(
        current_password=" old password ", new_password=" new password "
    )
    context = AccountRequestContext("token", "test", "https://test", "1")
    asyncio.run(UserService(database, gateway).change_password(command, context))
    gateway.change_password.assert_awaited_once_with(command, context)
    assert database.mock_calls == []
    assert "old password" not in repr(command)
    assert "token" not in repr(context)


def test_gateway_preserves_credentials_and_write_context() -> None:
    response = MagicMock(status=204)
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    command = ChangePasswordCommand(
        current_password=" old password ", new_password=" new password "
    )
    context = AccountRequestContext("session-token", "public:8021", "https://public:8021", "1")
    with patch("dvizh_backend.services.account_gateway.build_opener", return_value=opener):
        asyncio.run(AccountGateway("http://auth:8003/").change_password(command, context))
    request = opener.open.call_args.args[0]
    assert request.full_url == "http://auth:8003/api/auth/password"
    assert json.loads(request.data) == {
        "current_password": " old password ", "new_password": " new password ",
    }
    assert request.get_header("Cookie") == "dvizh_access=session-token"
    assert request.get_header("Host") == context.host
    assert request.get_header("Origin") == context.origin
    assert request.get_header("X-dvizh-account") == "1"


@pytest.mark.parametrize("status", [400, 401, 403, 422, 500, 302])
def test_gateway_sanitizes_errors(status: int) -> None:
    failure = HTTPError("http://auth", status, "upstream", {}, io.BytesIO(b"secret-password"))
    opener = MagicMock()
    opener.open.side_effect = failure
    with (
        patch("dvizh_backend.services.account_gateway.build_opener", return_value=opener),
        pytest.raises(AccountCommandError) as error,
    ):
            asyncio.run(AccountGateway("http://auth").change_password(
                ChangePasswordCommand(current_password="old", new_password="new"),
                AccountRequestContext("", "test", None, ""),
            ))
    assert error.value.status_code == (status if status in (400, 401, 403, 422) else 503)
    assert "secret-password" not in str(error.value)


def test_gateway_unavailable() -> None:
    opener = MagicMock()
    opener.open.side_effect = URLError("private connection details")
    with (
        patch("dvizh_backend.services.account_gateway.build_opener", return_value=opener),
        pytest.raises(AccountCommandError, match="Authentication service unavailable"),
    ):
            asyncio.run(AccountGateway("http://auth").change_password(
                ChangePasswordCommand(current_password="old", new_password="new"),
                AccountRequestContext("", "test", None, ""),
            ))


def test_password_http_command_and_sanitized_validation() -> None:
    async def scenario() -> None:
        service = MagicMock(change_password=AsyncMock())
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[get_user_service] = lambda: service
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://test"
            ) as client:
                response = await client.post("/api/personal/password", json={
                    "current_password": "old password", "new_password": "new password",
                }, headers={"Cookie": "dvizh_access=token", "X-Dvizh-Account": "1"})
                assert response.status_code == 204 and not response.content
                command, context = service.change_password.await_args.args
                assert command.new_password.get_secret_value() == "new password"
                assert context.token == "token" and context.write_header == "1"
                service.change_password.side_effect = AccountCommandError(
                    401, "Authentication required"
                )
                response = await client.post("/api/personal/password", json={
                    "current_password": "old password", "new_password": "new password",
                })
                assert response.status_code == 401
                response = await client.post("/api/personal/password", json={
                    "current_password": "old password", "new_password": "private-password" * 20,
                })
                assert response.status_code == 422
                assert "private-password" not in response.text
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
    asyncio.run(scenario())
