import asyncio
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest

from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import connect_databases

SOURCE_URL = "postgresql://reader:source-secret@source.invalid/source"
VECTOR_URL = "postgresql://writer:vector-secret@vector.invalid/vectors"


class Engine:
    def __init__(
        self, *, connection_error=None, probe_error=None, connect_hangs=False, dispose_hangs=False
    ):
        self.connection_error = connection_error
        self.probe_error = probe_error
        self.connect_hangs = connect_hangs
        self.disposed = False
        self.active = 0
        self.dispose_hangs = dispose_hangs

    @asynccontextmanager
    async def connect(self) -> AsyncIterator["Engine"]:
        if self.connect_hangs:
            await asyncio.Event().wait()
        if self.connection_error:
            raise self.connection_error
        self.active += 1
        try:
            yield self
        finally:
            self.active -= 1

    async def execute(self, statement):
        if self.probe_error:
            raise self.probe_error
        return Mock()

    async def dispose(self, *, close=True):
        self.disposed = True
        if close and self.dispose_hangs:
            await asyncio.Event().wait()


def database_settings() -> Settings:
    return Settings(
        source_database_url=SOURCE_URL,
        vector_database_url=VECTOR_URL,
        redis_url="redis://redis.invalid/0",
        database_timeout_seconds=0.02,
        _env_file=None,
    )


@pytest.mark.parametrize(
    ("failure", "dispose_hangs"), [("connect", False), ("probe", False), ("connect", True)]
)
def test_vector_failure_disposes_both_engines_without_leaking_credentials(
    monkeypatch, caplog, failure, dispose_hangs,
):
    error = OSError(f"Rejected credentials in {VECTOR_URL}")
    source = Engine(dispose_hangs=dispose_hangs)
    vector = Engine(connection_error=error) if failure == "connect" else Engine(probe_error=error)
    driver = Mock()
    driver.is_closed.return_value = not dispose_hangs

    def create_engine(dsn, *, live_connections, **kwargs):
        if dsn == SOURCE_URL:
            live_connections.add(driver)
            return source
        return vector

    monkeypatch.setattr("dvizh_recommendation.database.create_database_engine", create_engine)

    async def run():
        async with asyncio.timeout(1), connect_databases(database_settings()):
            pytest.fail("Startup succeeded with an unavailable vector database")

    with pytest.raises(RuntimeError, match="vector database") as caught:
        asyncio.run(run())
    assert source.disposed and vector.disposed
    assert source.active == vector.active == 0
    assert driver.terminate.call_count == int(dispose_hangs)
    diagnostics = "".join(traceback.format_exception(caught.value)) + caplog.text
    assert "source-secret" not in diagnostics and "vector-secret" not in diagnostics


@pytest.mark.parametrize("failure", ["timeout", "probe"])
def test_source_failure_aborts_startup_before_opening_vector_database(monkeypatch, failure):
    source = Engine(connect_hangs=True) if failure == "timeout" else Engine(probe_error=OSError())
    create_engine = Mock(return_value=source)
    monkeypatch.setattr("dvizh_recommendation.database.create_database_engine", create_engine)

    async def run():
        async with asyncio.timeout(1), connect_databases(database_settings()):
            pytest.fail("Startup succeeded with an unavailable source database")

    message = "source database.*TimeoutError" if failure == "timeout" else "source database"
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(run())
    assert source.disposed and source.active == 0
    create_engine.assert_called_once()
