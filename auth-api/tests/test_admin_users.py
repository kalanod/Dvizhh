import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from dvizh_auth.api.dependencies import get_session, require_account
from dvizh_auth.api.errors import register_error_handlers
from dvizh_auth.api.routers.admin import router
from dvizh_auth.database import Database
from dvizh_auth.models import ADMIN_ROLE_ID, USER_ROLE_ID, Account
from dvizh_auth.repository import AccountRepository
from dvizh_auth.services.account_service import (
    AccountNotFoundError,
    AccountService,
    AdminAccessDeniedError,
    SelfDemotionError,
    hash_password,
    password_hasher,
)


def account(role_id=USER_ROLE_ID, username="member"):
    return SimpleNamespace(
        id=uuid4(), username=username, email=None, role_id=role_id,
        role=SimpleNamespace(name="admin" if role_id == ADMIN_ROLE_ID else "user"),
        password_hash=hash_password("old-password"),
    )


def test_admin_commands_lock_and_revalidate_actor_before_any_mutation():
    async def scenario():
        actor, target = account(ADMIN_ROLE_ID, "admin"), account()
        service = AccountService(SimpleNamespace())
        service.accounts = SimpleNamespace(
            lock_accounts=AsyncMock(return_value={actor.id: actor, target.id: target}),
            flush=AsyncMock(),
        )
        with pytest.raises(SelfDemotionError):
            await service.change_role(actor.id, actor.id, "user")
        assert actor.role_id == ADMIN_ROLE_ID
        assert (await service.change_role(actor.id, target.id, "admin")).role_id == ADMIN_ROLE_ID
        await service.reset_password(actor.id, target.id, " new-admin-password ")
        assert password_hasher.verify(" new-admin-password ", target.password_hash)
        assert not password_hasher.verify("old-password", target.password_hash)
        service.accounts.lock_accounts.assert_awaited_with({actor.id, target.id})
        actor.role_id = USER_ROLE_ID
        unchanged = target.password_hash
        with pytest.raises(AdminAccessDeniedError):
            await service.reset_password(actor.id, target.id, "forbidden-password")
        assert target.password_hash == unchanged
        actor.role_id = ADMIN_ROLE_ID
        with pytest.raises(AccountNotFoundError):
            await service.change_role(actor.id, uuid4(), "user")

    asyncio.run(scenario())


def test_user_search_is_bounded_literal_and_never_returns_credential_hashes():
    async def scenario():
        users = [account(username=f"member_{i}") for i in range(3)]
        service = AccountService(SimpleNamespace())
        service.accounts = SimpleNamespace(search=AsyncMock(return_value=users))
        page = await service.search(" MEMBER ", 20, 2)
        service.accounts.search.assert_awaited_once_with("member", 20, 3)
        assert page.has_more and len(page.items) == 2 and page.offset == 20 and page.limit == 2
        assert "password" not in page.model_dump_json()
        session = SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(unique=lambda: [])),
        )
        repository = AccountRepository(session)
        await repository.search("%_", 0, 21)
        statement = session.scalars.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        assert "/%/_" in compiled.params.values()
        assert "ORDER BY accounts.username, accounts.id" in str(statement)
        await repository.lock_accounts({users[0].id, users[1].id})
        assert "ORDER BY accounts.id FOR UPDATE OF accounts" in str(
            session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        )

    asyncio.run(scenario())


def test_admin_routes_authorization_csrf_validation_and_secret_redaction():
    actor, target = account(ADMIN_ROLE_ID, "admin"), account()
    locked = {actor.id: actor, target.id: target}
    scalar_result = SimpleNamespace(unique=lambda: list(locked.values()))
    session = SimpleNamespace(scalars=AsyncMock(return_value=scalar_result), flush=AsyncMock())
    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_account] = lambda: actor
    root = "/api/auth/admin/users"
    headers = {"X-Dvizh-Admin": "1", "Origin": "http://testserver"}
    with TestClient(app) as client:
        assert client.get(root).status_code == 200
        actor.role.name = "user"
        assert client.get(root).status_code == 403
        assert client.patch(
            f"{root}/{target.id}/role", json={"role": "admin"}, headers=headers,
        ).status_code == 403
        actor.role.name = "admin"
        session.flush.reset_mock()
        for bad_headers in ({}, {**headers, "Origin": "https://evil.example"}):
            response = client.post(
                f"{root}/{target.id}/password", json={"new_password": "new-password"},
                headers=bad_headers,
            )
            assert response.status_code == 403
        session.flush.assert_not_awaited()
        for payload in ({"new_password": "short"}, {"new_password": "x" * 129},
                        {"new_password": "new-password", "role": "admin"}):
            response = client.post(f"{root}/{target.id}/password", json=payload, headers=headers)
            assert response.status_code == 422 and "new-password" not in response.text
        response = client.post(
            f"{root}/{target.id}/password", json={"new_password": "new-password"}, headers=headers,
        )
        assert response.status_code == 204 and not response.content
        assert password_hasher.verify("new-password", target.password_hash)
        response = client.patch(f"{root}/{target.id}/role", json={"role": "admin"}, headers=headers)
        assert response.status_code == 200 and response.json()["role"] == "admin"
        assert "password" not in response.text
        response = client.patch(f"{root}/{actor.id}/role", json={"role": "user"}, headers=headers)
        assert response.status_code == 409
        assert client.get(root, params={"limit": 101}).status_code == 422
        assert client.get(root, params={"offset": -1}).status_code == 422
        assert client.get(root, params={"q": "x" * 121}).status_code == 422


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_admin_mutual_demotion_cannot_remove_both_admins_and_password_reset_changes_login():
    async def scenario():
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        prefix = "admin_qa_" + uuid4().hex[:10]
        ids = [uuid4() for _ in range(3)]
        try:
            async with database.session() as session:
                session.add_all([
                    Account(
                        id=identifier, username=f"{prefix}_{index}", email=None,
                        role_id=ADMIN_ROLE_ID if index < 2 else USER_ROLE_ID,
                        password_hash=hash_password("old-password"),
                    )
                    for index, identifier in enumerate(ids)
                ])
            ready, started = asyncio.Event(), []

            async def demote(actor_id, target_id):
                async with database.session() as session:
                    # Both identities have already passed authentication before either mutation.
                    await session.get(Account, actor_id)
                    started.append(actor_id)
                    if len(started) == 2:
                        ready.set()
                    await ready.wait()
                    await AccountService(session).change_role(actor_id, target_id, "user")

            results = await asyncio.gather(
                demote(ids[0], ids[1]), demote(ids[1], ids[0]), return_exceptions=True,
            )
            assert sum(result is None for result in results) == 1
            assert sum(isinstance(result, AdminAccessDeniedError) for result in results) == 1
            async with database.session() as session:
                accounts = [await session.get(Account, identifier) for identifier in ids]
                admins = [account for account in accounts if account.role_id == ADMIN_ROLE_ID]
                assert len(admins) == 1
                service = AccountService(session)
                page = await service.search(prefix, 0, 1)
                assert len(page.items) == 1 and page.has_more
                assert "password" not in page.model_dump_json()
                assert not (await service.search("%", 0, 20)).items
                await service.reset_password(admins[0].id, ids[2], " new-password ")
            async with database.session() as session:
                service = AccountService(session)
                assert await service.authenticate(f"{prefix}_2", "old-password") is None
                assert (await service.authenticate(f"{prefix}_2", " new-password ")).id == ids[2]
        finally:
            await database.dispose()

    asyncio.run(scenario())
