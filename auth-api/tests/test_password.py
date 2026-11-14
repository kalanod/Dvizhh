import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_credentials import account_request

from dvizh_auth.dto import ChangePasswordRequest
from dvizh_auth.main import change_password, validation_error
from dvizh_auth.service import AccountService, InvalidCurrentPasswordError, hash_password


def test_password_policy_and_secrets() -> None:
    for fields in (
        {},
        {"current_password": "", "new_password": "new-password"},
        {"current_password": "old", "new_password": "short"},
        {"current_password": "old", "new_password": "x" * 129},
        {"current_password": "old", "new_password": "new-password", "id": str(uuid4())},
    ):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(**fields)
    command = ChangePasswordRequest(current_password=" old ", new_password=" new-password ")
    assert command.current_password.get_secret_value() == " old "
    assert command.new_password.get_secret_value() == " new-password "
    assert "new-password" not in repr(command)


def test_password_change_checks_current_hash_and_changes_login() -> None:
    async def scenario() -> None:
        account = SimpleNamespace(id=uuid4(), password_hash=hash_password(" old-password "))
        service = AccountService(SimpleNamespace())
        service.accounts = SimpleNamespace(
            get_for_update=AsyncMock(return_value=account),
            find=AsyncMock(return_value=account),
            flush=AsyncMock(),
        )
        original = account.password_hash
        with pytest.raises(InvalidCurrentPasswordError):
            await service.change_password(account.id, ChangePasswordRequest(
                current_password="wrong", new_password=" new-password ",
            ))
        assert account.password_hash == original
        service.accounts.flush.assert_not_awaited()
        await service.change_password(account.id, ChangePasswordRequest(
            current_password=" old-password ", new_password=" new-password ",
        ))
        assert account.password_hash != original
        assert "new-password" not in account.password_hash
        assert await service.authenticate("member", " old-password ") is None
        assert await service.authenticate("member", " new-password ") is account
        # A subsequent command with the old password cannot overwrite the first change.
        with pytest.raises(InvalidCurrentPasswordError):
            await service.change_password(account.id, ChangePasswordRequest(
                current_password=" old-password ", new_password="second-password",
            ))

    asyncio.run(scenario())


def test_password_route_auth_csrf_and_service_error() -> None:
    async def scenario() -> None:
        command = ChangePasswordRequest(current_password="old", new_password="new-password")
        session = SimpleNamespace(get=AsyncMock())
        with pytest.raises(HTTPException) as error:
            await change_password(command, account_request(), session)
        assert error.value.status_code == 401
        account = SimpleNamespace(id=uuid4())
        with patch("dvizh_auth.main.require_account", AsyncMock(return_value=account)), patch(
            "dvizh_auth.main.AccountService"
        ) as factory:
            service = factory.return_value
            service.change_password = AsyncMock()
            for headers in ({"x-dvizh-account": ""}, {"origin": "https://evil.example"}):
                with pytest.raises(HTTPException) as error:
                    await change_password(command, account_request(**headers), session)
                assert error.value.status_code == 403
            service.change_password.assert_not_awaited()
            service.change_password.side_effect = InvalidCurrentPasswordError
            with pytest.raises(HTTPException) as error:
                await change_password(command, account_request(), session)
            assert error.value.status_code == 400
            assert error.value.detail == "Invalid current password"
            service.change_password.side_effect = None
            response = await change_password(command, account_request(), session)
            assert response.status_code == 204 and response.body == b""
            service.change_password.assert_awaited_with(account.id, command)

    asyncio.run(scenario())


def test_validation_response_does_not_echo_password() -> None:
    from fastapi.exceptions import RequestValidationError

    error = RequestValidationError([
        {"type": "too_short", "loc": ("body", "new_password"), "msg": "Too short",
         "input": "secret-value", "ctx": {"value": "secret-value"}},
    ])
    response = asyncio.run(validation_error(account_request(), error))
    assert response.status_code == 422
    assert b"secret-value" not in response.body
