import argparse
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import asyncpg


@asynccontextmanager
async def connect_database(
    variable: str, *, command_timeout: float | None = 30
) -> AsyncIterator[asyncpg.Connection]:
    url = os.environ.get(variable)
    if not url:
        raise ValueError(f"{variable} is required")
    try:
        connection = await asyncpg.connect(url, timeout=5, command_timeout=command_timeout)
    except Exception as exc:
        raise RuntimeError(f"Cannot connect using {variable} ({type(exc).__name__})") from None
    try:
        yield connection
    finally:
        await connection.close(timeout=5)


def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise argparse.ArgumentTypeError("A time zone is required")
    return timestamp.astimezone(UTC)
