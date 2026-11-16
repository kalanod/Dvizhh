"""Exercise both schemas that historically shared the same Alembic revision ID."""

import asyncio
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from dvizh_auth.database import Database
from dvizh_auth.models import ADMIN_ROLE_ID, USER_ROLE_ID


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
@pytest.mark.parametrize("source", ["legacy_admin", "existing_roles", "both"])
def test_role_bridge_preserves_accounts_and_administrator_privileges(source: str) -> None:
    async def scenario() -> None:
        url = os.environ["TEST_DATABASE_URL"]
        assert make_url(url).database == "auth_roles_test"
        database = Database(url)
        admin_id, user_id = uuid4(), uuid4()
        path = Path(__file__).parents[1] / "alembic/versions/20261114_0002_account_roles.py"
        spec = importlib.util.spec_from_file_location("role_bridge", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)

        def exercise(connection) -> None:
            schema = "role_bridge_" + uuid4().hex
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            connection.exec_driver_sql(
                "CREATE TABLE accounts (id uuid PRIMARY KEY, email varchar(254) UNIQUE NOT NULL, "
                "password_hash text NOT NULL)"
            )
            if source in {"legacy_admin", "both"}:
                connection.exec_driver_sql(
                    "ALTER TABLE accounts ADD COLUMN is_admin boolean NOT NULL DEFAULT false"
                )
            if source in {"existing_roles", "both"}:
                connection.exec_driver_sql(
                    "CREATE TABLE roles (id uuid PRIMARY KEY, name varchar(20) UNIQUE NOT NULL, "
                    "CONSTRAINT ck_roles_name CHECK (name IN ('user', 'admin')))"
                )
                connection.execute(
                    text("INSERT INTO roles (id, name) VALUES (:id, :name)"),
                    [
                        {"id": ADMIN_ROLE_ID, "name": "admin"},
                        {"id": USER_ROLE_ID, "name": "user"},
                    ],
                )
                connection.exec_driver_sql(
                    "ALTER TABLE accounts ADD COLUMN role_id uuid NOT NULL "
                    f"DEFAULT '{USER_ROLE_ID}' CONSTRAINT fk_accounts_role_id_roles "
                    "REFERENCES roles(id) ON DELETE RESTRICT"
                )
            connection.execute(
                text("INSERT INTO accounts (id, email, password_hash) VALUES (:id, :email, :hash)"),
                [
                    {"id": admin_id, "email": "admin@example.org", "hash": "unchanged-admin-hash"},
                    {"id": user_id, "email": "user@example.org", "hash": "unchanged-user-hash"},
                ],
            )
            if source in {"legacy_admin", "both"}:
                connection.execute(
                    text("UPDATE accounts SET is_admin = true WHERE id = :id"), {"id": admin_id}
                )
            if source == "existing_roles":
                connection.execute(
                    text("UPDATE accounts SET role_id = :role WHERE id = :id"),
                    {"role": ADMIN_ROLE_ID, "id": admin_id},
                )
            with Operations.context(MigrationContext.configure(connection)):
                bridge.upgrade()
                assert "is_admin" not in {
                    c["name"] for c in inspect(connection).get_columns("accounts")
                }
                rows = {
                    row.id: row
                    for row in connection.execute(
                        text("SELECT id, password_hash, role_id FROM accounts")
                    )
                }
                assert rows[admin_id].role_id == ADMIN_ROLE_ID
                assert rows[user_id].role_id == USER_ROLE_ID
                assert rows[admin_id].password_hash == "unchanged-admin-hash"
                assert rows[user_id].password_hash == "unchanged-user-hash"
                bridge.downgrade()
                assert (
                    connection.scalar(
                        text("SELECT is_admin FROM accounts WHERE id = :id"), {"id": admin_id}
                    )
                    is True
                )
                bridge.upgrade()
                assert (
                    connection.scalar(
                        text("SELECT role_id FROM accounts WHERE id = :id"), {"id": admin_id}
                    )
                    == ADMIN_ROLE_ID
                )

        try:
            async with database.engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.run_sync(exercise)
                finally:
                    await transaction.rollback()
        finally:
            await database.dispose()

    asyncio.run(scenario())
