import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from starlette.requests import Request

from dvizh_auth.database import Database
from dvizh_auth.dependencies import require_account_write
from dvizh_auth.main import (
    LoginRequest,
    RegisterRequest,
    UpdateAccountRequest,
    current_account,
    login,
    register,
    update_current_account,
)


def account_request(cookie: str = "", **headers: str) -> Request:
    values = {"host": "test.local:8021", "x-dvizh-account": "1", "cookie": cookie, **headers}
    return Request(
        {
            "type": "http",
            "headers": [(name.encode(), value.encode()) for name, value in values.items()],
        }
    )


def test_usernames_are_required_and_email_is_optional() -> None:
    for email in (None, "", "   "):
        data = RegisterRequest(username=" MEMBER_1 ", email=email, password="password123")
        assert data.username == "member_1"
        assert data.email is None
    assert RegisterRequest(username="member", password="password123").email is None
    assert (
        RegisterRequest(
            username="member",
            email=" MEMBER@EXAMPLE.ORG ",
            password="password123",
        ).email
        == "member@example.org"
    )
    for username in (None, "", "ab", "a" * 51, "user-name", "a@b.com", "two words"):
        with pytest.raises(ValidationError):
            RegisterRequest(username=username, password="password123")
    with pytest.raises(ValidationError):
        RegisterRequest(password="password123")
    for fields in ({}, {"username": None}, {"role": "admin"}, {"email": "invalid"}):
        with pytest.raises(ValidationError):
            UpdateAccountRequest(**fields)
    assert UpdateAccountRequest(email="").model_dump(exclude_unset=True) == {"email": None}
    assert UpdateAccountRequest(username=" MEMBER_2 ").username == "member_2"


def test_account_writes_require_non_simple_header_and_matching_origin() -> None:
    for headers in (
        {"x-dvizh-account": ""},
        {"origin": "https://evil.example"},
        {"origin": "https://test.local:9999"},
        {"origin": "null"},
        {"origin": "http://[invalid"},
    ):
        with pytest.raises(HTTPException) as error:
            require_account_write(account_request(**headers))
        assert error.value.status_code == 403
    require_account_write(account_request(origin="https://test.local:8021"))
    require_account_write(account_request())


def test_account_patch_requires_authentication() -> None:
    async def scenario() -> None:
        session = SimpleNamespace(get=AsyncMock())
        with pytest.raises(HTTPException) as error:
            await update_current_account(
                UpdateAccountRequest(username="new_name"),
                account_request(),
                session,
            )
        assert error.value.status_code == 401
        session.get.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_registration_login_and_authenticated_account_changes() -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        first_username = "u_" + uuid4().hex
        second_username = "u_" + uuid4().hex
        email = uuid4().hex + "@example.org"
        password = "test-password"
        try:
            async with database.session() as session:
                first = await register(
                    RegisterRequest(
                        username=first_username,
                        email=email,
                        password=password,
                    ),
                    session,
                )
                second = await register(
                    RegisterRequest(
                        username=second_username,
                        password=password,
                    ),
                    session,
                )
                third = await register(
                    RegisterRequest(
                        username="u_" + uuid4().hex,
                        email="",
                        password=password,
                    ),
                    session,
                )
                assert second.email is None and third.email is None
                for fields in (
                    {"username": first_username.upper()},
                    {"username": "u_" + uuid4().hex, "email": email.upper()},
                ):
                    with pytest.raises(HTTPException) as error:
                        await register(RegisterRequest(password=password, **fields), session)
                    assert error.value.status_code == 409
            for identifier in (first_username.upper(), email.upper()):
                async with database.session() as session:
                    response = await login(
                        LoginRequest(login=identifier, password=password), session
                    )
                    assert response.status_code == 204
                    cookie = response.headers["set-cookie"].split(";", 1)[0]
                    assert (await current_account(account_request(cookie), session)).id == first.id
            for headers in ({"x-dvizh-account": ""}, {"origin": "https://evil.example"}):
                async with database.session() as session:
                    with pytest.raises(HTTPException) as error:
                        await update_current_account(
                            UpdateAccountRequest(email=None),
                            account_request(cookie, **headers),
                            session,
                        )
                    assert error.value.status_code == 403
            for data in (
                UpdateAccountRequest(username=first_username.upper()),
                UpdateAccountRequest(email=email.upper()),
            ):
                async with database.session() as session:
                    response = await login(
                        LoginRequest(
                            login=second_username,
                            password=password,
                        ),
                        session,
                    )
                    second_cookie = response.headers["set-cookie"].split(";", 1)[0]
                    with pytest.raises(HTTPException) as error:
                        await update_current_account(data, account_request(second_cookie), session)
                    assert error.value.status_code == 409
            new_username = "u_" + uuid4().hex
            async with database.session() as session:
                changed = await update_current_account(
                    UpdateAccountRequest(username=new_username.upper(), email=""),
                    account_request(cookie, origin="https://test.local:8021"),
                    session,
                )
                assert changed.id == first.id
                assert changed.username == new_username
                assert changed.email is None
                assert changed.role == "user"
            async with database.session() as session:
                assert (
                    await current_account(account_request(cookie), session)
                ).username == new_username
                for old_login in (first_username, email):
                    with pytest.raises(HTTPException) as error:
                        await login(LoginRequest(login=old_login, password=password), session)
                    assert error.value.status_code == 401
                assert (
                    await login(
                        LoginRequest(
                            login=new_username,
                            password=password,
                        ),
                        session,
                    )
                ).status_code == 204
        finally:
            await database.dispose()

    asyncio.run(scenario())
