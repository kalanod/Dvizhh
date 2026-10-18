import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
from pydantic import SecretStr

from .config import Settings


@dataclass(frozen=True)
class Databases:
    source: asyncpg.Pool
    vector: asyncpg.Pool


@asynccontextmanager
async def _connected_pool(
    name: str, url: SecretStr, settings: Settings
) -> AsyncIterator[asyncpg.Pool]:
    pool = None
    try:
        try:
            async with asyncio.timeout(settings.database_timeout_seconds):
                pool = asyncpg.create_pool(
                    url.get_secret_value(),
                    min_size=settings.database_pool_min_size,
                    max_size=settings.database_pool_max_size,
                    timeout=settings.database_timeout_seconds,
                    command_timeout=settings.database_timeout_seconds,
                )
                await pool
                async with pool.acquire(timeout=settings.database_timeout_seconds) as connection:
                    await connection.fetchval("SELECT 1")
        except Exception as exc:
            raise RuntimeError(
                f"Cannot connect to {name} database ({type(exc).__name__})"
            ) from None
        yield pool
    finally:
        if pool is not None:
            try:
                async with asyncio.timeout(settings.database_timeout_seconds):
                    await pool.close()
            except TimeoutError:
                pool.terminate()


@asynccontextmanager
async def connect_databases(settings: Settings) -> AsyncIterator[Databases]:
    async with (
        _connected_pool("source", settings.source_database_url, settings) as source,
        _connected_pool("vector", settings.vector_database_url, settings) as vector,
    ):
        yield Databases(source=source, vector=vector)
