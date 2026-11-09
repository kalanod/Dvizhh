import asyncio
import traceback
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from dvizh_recommendation.config import Settings
from dvizh_recommendation.main import running_server

REDIS_URL = "redis://:redis-secret@redis.invalid/0"


@pytest.mark.parametrize("unresponsive", [False, True])
def test_failed_redis_startup_closes_connections_without_leaking_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    unresponsive: bool,
) -> None:
    closed = []

    class Client:
        async def ping(self):
            if unresponsive:
                await asyncio.Event().wait()
            raise ConnectionError(f"Cannot connect to {REDIS_URL}")

        async def aclose(self):
            closed.append("redis")

    @asynccontextmanager
    async def connect_databases(_settings):
        try:
            yield SimpleNamespace(source=None, vector=None)
        finally:
            closed.append("databases")

    monkeypatch.setattr("dvizh_recommendation.main.connect_databases", connect_databases)
    monkeypatch.setattr(
        "dvizh_recommendation.redis.Redis.from_url", lambda *args, **kwargs: Client()
    )
    settings = Settings(
        source_database_url="postgresql://source.invalid/source",
        vector_database_url="postgresql://vector.invalid/vector",
        redis_url=REDIS_URL,
        redis_timeout_seconds=0.02,
        _env_file=None,
    )

    async def run():
        async with asyncio.timeout(1):
            async with running_server(settings):
                pytest.fail("Server started while Redis was unavailable")

    cause = "TimeoutError" if unresponsive else "ConnectionError"
    with pytest.raises(RuntimeError, match=f"Cannot connect to Redis.*{cause}") as error:
        asyncio.run(run())

    assert closed == ["redis", "databases"]
    diagnostics = "".join(traceback.format_exception(error.value)) + caplog.text
    assert REDIS_URL not in diagnostics
    assert "redis-secret" not in diagnostics
