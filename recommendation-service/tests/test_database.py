import asyncio
import traceback
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager

import pytest

from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import connect_databases

SOURCE_URL = "postgresql://reader:source-secret@source.invalid/source"
VECTOR_URL = "postgresql://writer:vector-secret@vector.invalid/vectors"


class Pool:
    def __init__(
        self,
        *,
        close_hangs: bool = False,
        initialize_hangs: bool = False,
        initialize_error: Exception | None = None,
    ) -> None:
        self.close_hangs = close_hangs
        self.initialize_hangs = initialize_hangs
        self.initialize_error = initialize_error
        self.close_called = False
        self.terminated = False

    def __await__(self) -> Generator[None, None, "Pool"]:
        return self.initialize().__await__()

    async def initialize(self) -> "Pool":
        if self.initialize_hangs:
            await asyncio.Event().wait()
        if self.initialize_error is not None:
            raise self.initialize_error
        return self

    @asynccontextmanager
    async def acquire(self, **_kwargs: object) -> AsyncIterator["Pool"]:
        yield self

    async def fetchval(self, *_args: object) -> int:
        return 1

    async def close(self) -> None:
        self.close_called = True
        if self.close_hangs:
            await asyncio.Event().wait()

    def terminate(self) -> None:
        self.terminated = True


def database_settings() -> Settings:
    return Settings(
        source_database_url=SOURCE_URL,
        vector_database_url=VECTOR_URL,
        database_timeout_seconds=0.02,
        _env_file=None,
    )


@pytest.mark.parametrize("close_hangs", [False, True])
def test_vector_connection_failure_releases_source_without_leaking_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, close_hangs: bool
) -> None:
    source = Pool(close_hangs=close_hangs)
    vector = Pool(initialize_error=OSError(f"Rejected credentials in {VECTOR_URL}"))
    attempts = 0

    def create_pool(*_args: object, **_kwargs: object) -> Pool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return source
        return vector

    monkeypatch.setattr("dvizh_recommendation.database.asyncpg.create_pool", create_pool)

    async def run() -> None:
        async with asyncio.timeout(1):
            async with connect_databases(database_settings()):
                pytest.fail("Startup succeeded while the vector database was unavailable")

    with pytest.raises(RuntimeError, match="vector database") as error:
        asyncio.run(run())

    assert source.close_called
    assert vector.close_called
    assert source.terminated is close_hangs
    diagnostics = "".join(traceback.format_exception(error.value)) + caplog.text
    assert "source-secret" not in diagnostics
    assert "vector-secret" not in diagnostics
    assert SOURCE_URL not in diagnostics
    assert VECTOR_URL not in diagnostics


def test_unresponsive_database_connection_has_bounded_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Pool(initialize_hangs=True)

    def create_pool(*_args: object, **_kwargs: object) -> Pool:
        return source

    monkeypatch.setattr("dvizh_recommendation.database.asyncpg.create_pool", create_pool)

    async def run() -> None:
        async with asyncio.timeout(1):
            async with connect_databases(database_settings()):
                pytest.fail("Startup succeeded while the source database was unresponsive")

    with pytest.raises(RuntimeError, match="source database.*TimeoutError"):
        asyncio.run(run())

    assert source.close_called
