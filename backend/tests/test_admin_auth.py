from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from dvizh_backend.services import admin_auth


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()

    @app.api_route(
        "/admin", methods=["GET", "POST"], dependencies=[Depends(admin_auth.require_admin)]
    )
    async def protected():
        return {"ok": True}

    monkeypatch.setattr(
        admin_auth, "_fetch_account",
        lambda *_: admin_auth.AdminAccount(id=uuid4(), is_admin=True),
    )
    with TestClient(app) as http:
        yield http


def test_admin_requires_authenticated_cookie(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin?user_id=admin").status_code == 401


def test_admin_checks_current_account_privilege(client, monkeypatch):
    client.cookies.set("dvizh_access", "session-token")
    assert client.get("/admin").status_code == 200
    monkeypatch.setattr(
        admin_auth, "_fetch_account",
        lambda *_: admin_auth.AdminAccount(id=uuid4(), is_admin=False),
    )
    assert client.get("/admin").status_code == 403


def test_admin_writes_reject_cross_origin_requests(client):
    client.cookies.set("dvizh_access", "session-token")
    assert client.post("/admin").status_code == 403
    headers = {"X-Dvizh-Admin": "1", "Origin": "https://other.example"}
    assert client.post("/admin", headers=headers).status_code == 403
    headers["Origin"] = "http://testserver"
    assert client.post("/admin", headers=headers).status_code == 200


def test_admin_auth_outage_fails_closed(client, monkeypatch):
    def unavailable(*_):
        raise admin_auth.HTTPException(503, "Authentication service unavailable")

    monkeypatch.setattr(admin_auth, "_fetch_account", unavailable)
    client.cookies.set("dvizh_access", "session-token")
    assert client.get("/admin").status_code == 503
