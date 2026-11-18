import argparse
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.pool import NullPool

from .database import create_database_engine


@asynccontextmanager
async def connect_database(
    variable: str, *, command_timeout: float | None = 30
) -> AsyncIterator[AsyncConnection]:
    url = os.environ.get(variable)
    if not url:
        raise ValueError(f"{variable} is required")
    engine = create_database_engine(url, command_timeout=command_timeout, poolclass=NullPool)
    async with AsyncExitStack() as resources:
        resources.push_async_callback(engine.dispose)
        try:
            connection = await resources.enter_async_context(engine.connect())
        except Exception as exc:
            raise RuntimeError(f"Cannot connect using {variable} ({type(exc).__name__})") from None
        yield connection


def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise argparse.ArgumentTypeError("A time zone is required")
    return timestamp.astimezone(UTC)
