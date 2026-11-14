"""Opt-in command-chain test against the disposable password QA auth service."""

import asyncio
import os
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from dvizh_backend.main import app
from dvizh_backend.services.account_gateway import AccountGateway
from dvizh_backend.services.dependencies import get_user_service
from dvizh_backend.services.user_service import UserService


@pytest.mark.skipif(
    not os.getenv("PASSWORD_AUTH_TEST_URL"), reason="Requires disposable password QA auth service"
)
def test_password_command_chain_with_real_auth_and_postgres() -> None:
    async def scenario() -> None:
        auth_url = os.environ["PASSWORD_AUTH_TEST_URL"]
        assert urlsplit(auth_url).hostname == "dvizh-password-auth-http"
        username = "qa_" + uuid4().hex
        password = " old-test-password "
        new_password = " new-test-password "
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[get_user_service] = lambda: UserService(
            AsyncMock(), AccountGateway(auth_url)
        )
        try:
            async with (
                httpx.AsyncClient(base_url=auth_url, trust_env=False) as auth,
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="https://public.test"
                ) as backend,
            ):
                response = await auth.post("/api/auth/register", json={
                    "username": username, "password": password,
                })
                assert response.status_code == 201
                response = await auth.post("/api/auth/login", json={
                    "login": username, "password": password,
                })
                assert response.status_code == 204
                token = response.cookies["dvizh_access"]
                body = {"current_password": password, "new_password": new_password}
                response = await backend.post("/api/personal/password", json=body)
                assert response.status_code == 401
                backend.cookies.set("dvizh_access", token)
                response = await backend.post("/api/personal/password", json=body)
                assert response.status_code == 403
                backend.headers["X-Dvizh-Account"] = "1"
                response = await backend.post("/api/personal/password", json=body, headers={
                    "Origin": "https://evil.test",
                })
                assert response.status_code == 403
                backend.headers["Origin"] = "https://public.test"
                response = await backend.post("/api/personal/password", json={
                    **body, "current_password": "wrong-password",
                })
                assert response.status_code == 400
                response = await backend.post("/api/personal/password", json=body)
                assert response.status_code == 204 and not response.content
                for candidate, expected in ((password, 401), (new_password, 204)):
                    response = await auth.post("/api/auth/login", json={
                        "login": username, "password": candidate,
                    })
                    assert response.status_code == expected
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
    asyncio.run(scenario())
