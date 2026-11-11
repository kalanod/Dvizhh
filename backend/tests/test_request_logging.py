import json

from dvizh_logging import JsonFormatter
from fastapi.testclient import TestClient

from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.main import app


def test_failed_request_keeps_id_and_logs_safe_error(monkeypatch, caplog) -> None:
    secret = "test-private-password"

    def fail_to_connect(*args, **kwargs):
        raise ConnectionRefusedError(secret)

    database = DatabaseService("postgresql+asyncpg://test@127.0.0.1:1/test")
    monkeypatch.setattr(database.engine.sync_engine.dialect, "connect", fail_to_connect)
    monkeypatch.setattr(app.state, "database_service", database, raising=False)
    monkeypatch.setattr(caplog.handler, "formatter", JsonFormatter("backend"))
    request_id = "1234567890abcdef1234567890abcdef"
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 500
    assert response.headers.get_list("X-Request-ID") == [request_id]
    records = [json.loads(line) for line in caplog.text.splitlines()]
    dependency, record = records
    assert dependency["dependency"] == "postgres"
    assert dependency["status"] == "ERROR"
    assert dependency["request_id"] == request_id
    assert dependency["error_type"] == "ConnectionRefusedError"
    assert record["level"] == "ERROR"
    assert record["operation"] == "GET /api/health"
    assert record["request_id"] == request_id
    assert record["status"] == 500
    assert record["error_type"] == "ConnectionRefusedError"
    assert "fail_to_connect" in str(record["error_stack"])
    assert secret not in caplog.text
    assert secret not in response.text
