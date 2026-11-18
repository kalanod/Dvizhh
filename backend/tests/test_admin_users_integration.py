"""Real credential-owner HTTP boundary; only a disposable auth_roles_test DB is accepted."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from dvizh_backend.api.errors import register_error_handlers
from dvizh_backend.api.routers.admin import router
from dvizh_backend.config import Settings, get_settings


@pytest.mark.skipif(
    not os.getenv("TEST_AUTH_URL") or not os.getenv("TEST_AUTH_DATABASE_URL"),
    reason="Requires disposable auth-api and auth_roles_test PostgreSQL",
)
def test_admin_gateway_real_auth_owner_role_changes_and_password_login():
    auth_url = os.environ["TEST_AUTH_URL"]
    database_url = os.environ["TEST_AUTH_DATABASE_URL"]
    assert make_url(database_url).database == "auth_roles_test"
    accounts = []
    prefix = "gateway_qa_" + uuid4().hex[:10]
    old_password, new_password = "qa-old-password", " qa-new-password "

    async def execute(sql, **params):
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(sql), params)
        finally:
            await engine.dispose()

    try:
        with httpx.Client(base_url=auth_url, timeout=10) as auth:
            for suffix in ("admin", "member"):
                response = auth.post("/api/auth/register", json={
                    "username": f"{prefix}_{suffix}", "password": old_password,
                })
                assert response.status_code == 201
                accounts.append(response.json())
            admin_id, member_id = [account["id"] for account in accounts]
            asyncio.run(execute(
                "UPDATE accounts SET role_id=(SELECT id FROM roles WHERE name='admin') "
                "WHERE id=CAST(:id AS uuid)", id=admin_id,
            ))
            assert auth.post("/api/auth/login", json={
                "login": accounts[0]["username"], "password": old_password,
            }).status_code == 204
            cookie = auth.cookies.get("dvizh_access")
            app = FastAPI()
            app.include_router(router)
            register_error_handlers(app)
            app.dependency_overrides[get_settings] = lambda: Settings(auth_url=auth_url)
            headers = {"X-Dvizh-Admin": "1", "Origin": "http://testserver"}
            with TestClient(app) as backend:
                backend.cookies.set("dvizh_access", cookie)
                response = backend.get("/api/admin/users", params={"q": prefix, "limit": 1})
                assert response.status_code == 200
                assert response.json()["has_more"] and len(response.json()["items"]) == 1
                assert "password" not in response.text
                response = backend.get("/api/admin/users", params={"q": prefix, "offset": 1})
                assert len(response.json()["items"]) == 1
                response = backend.patch(f"/api/admin/users/{member_id}/role", headers=headers,
                                         json={"role": "admin"})
                assert response.status_code == 200 and response.json()["role"] == "admin"
                response = backend.post(f"/api/admin/users/{member_id}/password", headers=headers,
                                        json={"new_password": new_password})
                assert response.status_code == 204 and not response.content
                assert auth.post("/api/auth/login", json={
                    "login": accounts[1]["username"], "password": old_password,
                }).status_code == 401
                assert auth.post("/api/auth/login", json={
                    "login": accounts[1]["username"], "password": new_password,
                }).status_code == 204
                member_cookie = auth.cookies.get("dvizh_access")
                assert auth.get("/api/auth/me").json()["role"] == "admin"
                response = backend.patch(f"/api/admin/users/{admin_id}/role", headers=headers,
                                         json={"role": "user"})
                assert response.status_code == 409
                response = backend.patch(f"/api/admin/users/{member_id}/role", headers=headers,
                                         json={"role": "user"})
                assert response.status_code == 200
                backend.cookies.set("dvizh_access", member_cookie)
                assert backend.get("/api/admin/users").status_code == 403
                assert backend.post(f"/api/admin/users/{admin_id}/password", headers=headers,
                                    json={"new_password": "forbidden-password"}).status_code == 403
    finally:
        for account in accounts:
            asyncio.run(execute(
                "DELETE FROM accounts WHERE id=CAST(:id AS uuid)", id=account["id"],
            ))
