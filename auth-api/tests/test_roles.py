import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from dvizh_auth.config import Settings
from dvizh_auth.database import Database
from dvizh_auth.dependencies import require_admin
from dvizh_auth.main import LoginRequest, RegisterRequest, current_account, login, register
from dvizh_auth.models import ADMIN_ROLE_ID, USER_ROLE_ID, Account, Role


def test_registration_cannot_select_role() -> None:
    for fields in ({"role": "admin"}, {"role_id": str(ADMIN_ROLE_ID)}):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="test_user", email="test@example.org", password="password123", **fields
            )


def test_temporary_jwt_secrets_are_unpredictable_and_explicit_keys_are_validated() -> None:
    first = Settings(_env_file=None, jwt_secret="")
    second = Settings(_env_file=None, jwt_secret="")
    assert first.jwt_secret != second.jwt_secret
    assert len(Settings(_env_file=None, jwt_secret="").jwt_secret) >= 32
    assert len(Settings(_env_file=None, jwt_secret="  ").jwt_secret) >= 32
    assert Settings(_env_file=None, jwt_secret="x" * 32).jwt_secret == "x" * 32
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="short")


def test_require_admin_checks_current_account_role() -> None:
    async def scenario() -> None:
        account = SimpleNamespace(role=SimpleNamespace(name="user"))
        with pytest.raises(HTTPException) as error:
            await require_admin(account)
        assert error.value.status_code == 403
        account.role.name = "admin"
        assert await require_admin(account) is account

    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_registration_promotion_and_revocation_with_same_session_cookie() -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        email = f"roles-{uuid4().hex}@example.org"
        try:
            async with database.session() as session:
                roles = {role.name: role.id for role in await session.scalars(select(Role))}
                assert roles == {"user": USER_ROLE_ID, "admin": ADMIN_ROLE_ID}
                created = await register(
                    RegisterRequest(
                        username="u_" + uuid4().hex, email=email, password="test-password"
                    ),
                    session,
                )
                account_id = created.id
                account = await session.get(Account, account_id)
                assert account.role_id == USER_ROLE_ID
                response = await login(
                    LoginRequest(login=email, password="test-password"),
                    session,
                )
                cookie = response.headers["set-cookie"].split(";", 1)[0]
            request = Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})
            async with database.session() as session:
                assert (await current_account(request, session)).role == "user"
                await session.execute(
                    update(Account).where(Account.id == account_id).values(role_id=ADMIN_ROLE_ID)
                )
            async with database.session() as session:
                assert (await current_account(request, session)).role == "admin"
                assert await require_admin(await session.get(Account, account_id))
                await session.execute(
                    update(Account).where(Account.id == account_id).values(role_id=USER_ROLE_ID)
                )
            async with database.session() as session:
                assert (await current_account(request, session)).role == "user"
                with pytest.raises(HTTPException) as error:
                    await require_admin(await session.get(Account, account_id))
                assert error.value.status_code == 403
        finally:
            await database.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_database_requires_one_existing_role_and_defaults_to_user() -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        email = f"db-default-{uuid4().hex}@example.org"
        try:
            async with database.session() as session:
                role_id = await session.scalar(
                    text(
                        "INSERT INTO accounts (id, username, email, password_hash) "
                        "VALUES (:id, :username, :email, :password_hash) RETURNING role_id"
                    ),
                    {
                        "id": uuid4(),
                        "username": "db_" + uuid4().hex,
                        "email": email,
                        "password_hash": "test-only",
                    },
                )
                assert role_id == USER_ROLE_ID
                for statement, params in (
                    ("INSERT INTO roles (id, name) VALUES (:id, 'owner')", {"id": uuid4()}),
                    ("DELETE FROM roles WHERE id = :id", {"id": USER_ROLE_ID}),
                    (
                        "UPDATE accounts SET role_id = NULL WHERE email = :email",
                        {"email": email},
                    ),
                    (
                        "UPDATE accounts SET role_id = :id WHERE email = :email",
                        {"id": uuid4(), "email": email},
                    ),
                ):
                    with pytest.raises(IntegrityError):
                        async with session.begin_nested():
                            await session.execute(text(statement), params)
        finally:
            await database.dispose()

    asyncio.run(scenario())
