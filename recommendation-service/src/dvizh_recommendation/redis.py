import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from .config import Settings


@asynccontextmanager
async def connect_redis(settings: Settings) -> AsyncIterator[Redis]:
    client = None
    try:
        try:
            client = Redis.from_url(
                settings.redis_url.get_secret_value(),
                decode_responses=True,
                socket_connect_timeout=settings.redis_timeout_seconds,
                socket_timeout=settings.redis_timeout_seconds,
                retry=Retry(NoBackoff(), 0),
            )
            async with asyncio.timeout(settings.redis_timeout_seconds):
                await client.ping()
        except Exception as exc:
            raise RuntimeError(f"Cannot connect to Redis ({type(exc).__name__})") from None
        yield client
    finally:
        if client is not None:
            async with asyncio.timeout(settings.redis_timeout_seconds):
                await client.aclose()
