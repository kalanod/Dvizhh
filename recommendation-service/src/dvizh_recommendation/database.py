import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any
from weakref import WeakSet

import asyncpg
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .config import Settings


@dataclass(frozen=True)
class Databases:
    source: AsyncEngine
    vector: AsyncEngine


def create_database_engine(
    dsn: str, *, connect_timeout: float = 5, command_timeout: float | None = 30,
    live_connections: WeakSet[asyncpg.Connection] | None = None, **pool_options: Any,
) -> AsyncEngine:
    async def connect() -> asyncpg.Connection:
        driver = await asyncpg.connect(
            dsn, timeout=connect_timeout, command_timeout=command_timeout
        )
        if live_connections is not None:
            live_connections.add(driver)
        return driver

    return create_async_engine(
        "postgresql+asyncpg://", async_creator=connect,
        hide_parameters=True,
        **pool_options,
    )


@asynccontextmanager
async def read_snapshot(connection: AsyncConnection) -> AsyncIterator[None]:
    previous = connection.sync_connection.get_execution_options()
    await connection.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)
    try:
        async with connection.begin():
            yield
    finally:
        if not connection.closed and not connection.invalidated:
            await connection.execution_options(
                isolation_level=previous.get("isolation_level", connection.default_isolation_level),
                postgresql_readonly=previous.get("postgresql_readonly", False),
            )


@asynccontextmanager
async def _connected_pool(
    name: str, url: SecretStr, settings: Settings,
) -> AsyncIterator[AsyncEngine]:
    timeout = settings.database_timeout_seconds
    drivers: WeakSet[asyncpg.Connection] = WeakSet()
    engine = create_database_engine(
        url.get_secret_value(), connect_timeout=timeout, command_timeout=timeout,
        pool_size=settings.database_pool_max_size, max_overflow=0, pool_timeout=timeout,
        live_connections=drivers,
    )
    try:
        try:
            async with asyncio.timeout(timeout), AsyncExitStack() as startup:
                for _ in range(settings.database_pool_min_size):
                    connection = await startup.enter_async_context(engine.connect())
                    await connection.execute(select(1))
        except Exception as exc:
            raise RuntimeError(
                f"Cannot connect to {name} database ({type(exc).__name__})"
            ) from None
        yield engine
    finally:
        try:
            with suppress(TimeoutError):
                async with asyncio.timeout(timeout):
                    await engine.dispose()
        finally:
            for driver in drivers:
                if not driver.is_closed():
                    driver.terminate()


@asynccontextmanager
async def connect_databases(settings: Settings) -> AsyncIterator[Databases]:
    async with (
        _connected_pool("source", settings.source_database_url, settings) as source,
        _connected_pool("vector", settings.vector_database_url, settings) as vector,
    ):
        yield Databases(source=source, vector=vector)
