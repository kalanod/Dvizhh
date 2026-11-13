import asyncio
import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import make_url
from starlette.requests import Request

from alembic import command
from dvizh_auth.database import Database
from dvizh_auth.main import LoginRequest, RegisterRequest, current_account, login
from dvizh_auth.models import ADMIN_ROLE_ID, USER_ROLE_ID, Account
from dvizh_auth.service import hash_password, password_hasher

ADMIN_ID = UUID("d035b112-2cdf-5d23-9361-5db5dc3f162c")


def test_usernames_and_valid_emails_are_accepted_for_login() -> None:
    assert LoginRequest(login=" ADMIN ", password="admin").login == "admin"
    assert (
        LoginRequest(login=" MEMBER@EXAMPLE.ORG ", password="secret").login == "member@example.org"
    )
    for invalid in ("", "ab", "bad-name", "admin@", "test name"):
        with pytest.raises(ValidationError):
            LoginRequest(login=invalid, password="admin")
    for fields in (
        {"username": "test_user", "email": "admin", "password": "long-enough-password"},
        {"username": "test_user", "email": "user@example.org", "password": "admin"},
    ):
        with pytest.raises(ValidationError):
            RegisterRequest(**fields)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_bootstrap_admin_can_login_and_has_administrator_role() -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        try:
            async with database.session() as session:
                account = await session.get(Account, ADMIN_ID)
                assert account is not None
                assert account.username == "admin"
                assert account.email is None
                assert account.role_id == ADMIN_ROLE_ID
                assert account.password_hash.startswith("$argon2")
                assert account.password_hash != "admin"
                assert password_hasher.verify("admin", account.password_hash)
                with pytest.raises(HTTPException) as error:
                    await login(LoginRequest(login="admin", password="wrong-password"), session)
                assert error.value.status_code == 401
                response = await login(LoginRequest(login=" ADMIN ", password="admin"), session)
                assert response.status_code == 204
                cookie = response.headers["set-cookie"].split(";", 1)[0]
                request = Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})
                current = await current_account(request, session)
                assert current.id == ADMIN_ID
                assert current.role == "admin"
        finally:
            await database.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_bootstrap_seed_does_not_reset_existing_password_or_role() -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        original = None
        try:
            async with database.session() as session:
                account = await session.get(Account, ADMIN_ID)
                original = account.password_hash, account.role_id
                changed_hash = hash_password("changed-test-password")
                account.password_hash = changed_hash
                account.role_id = USER_ROLE_ID
            root = Path(__file__).parents[1]
            config = Config(str(root / "alembic.ini"))
            config.set_main_option("script_location", str(root / "alembic"))
            await asyncio.to_thread(command.upgrade, config, "head")
            async with database.session() as session:
                account = await session.get(Account, ADMIN_ID)
                assert account.password_hash == changed_hash
                assert account.role_id == USER_ROLE_ID
                assert (
                    len(
                        list(
                            await session.scalars(
                                select(Account).where(Account.username == "admin")
                            )
                        )
                    )
                    == 1
                )
        finally:
            if original is not None:
                async with database.session() as session:
                    account = await session.get(Account, ADMIN_ID)
                    account.password_hash, account.role_id = original
            await database.dispose()

    asyncio.run(scenario())
