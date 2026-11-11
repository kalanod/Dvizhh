import asyncio
import logging
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import partial

import grpc
from dvizh_logging import configure_logging, error_fields
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from redis.asyncio import Redis

from .candidates import LatestRecommendations
from .catalog import filter_available_items
from .config import Settings, get_settings
from .database import Databases, connect_databases
from .generated import recommendation_service_pb2_grpc
from .pagination import Pagination, SessionStore
from .redis import connect_redis
from .service import SERVICE_NAME, RecommendationService

HEALTH_CHECK_INTERVAL_SECONDS = 5
logger = logging.getLogger(__name__)


async def _monitor_dependencies(
    settings: Settings,
    databases: Databases,
    redis: Redis,
    health_service: health.aio.HealthServicer,
) -> None:
    unavailable: set[str] = set()
    while True:
        results = await asyncio.gather(
            asyncio.wait_for(redis.ping(), timeout=settings.redis_timeout_seconds),
            asyncio.wait_for(
                databases.source.fetchval("SELECT 1"), timeout=settings.database_timeout_seconds
            ),
            asyncio.wait_for(
                databases.vector.fetchval("SELECT 1"), timeout=settings.database_timeout_seconds
            ),
            return_exceptions=True,
        )
        for dependency, result in zip(("redis", "postgres", "pgvector"), results, strict=True):
            if isinstance(result, BaseException):
                if dependency not in unavailable:
                    logger.warning(
                        "Dependency unavailable",
                        extra={"dependency": dependency, "error_type": type(result).__name__},
                    )
                    unavailable.add(dependency)
            elif dependency in unavailable:
                logger.info("Dependency recovered", extra={"dependency": dependency})
                unavailable.remove(dependency)

        if unavailable:
            status = health_pb2.HealthCheckResponse.NOT_SERVING
        else:
            status = health_pb2.HealthCheckResponse.SERVING
        await health_service.set("", status)
        await health_service.set(SERVICE_NAME, status)
        await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def running_server(
    settings: Settings,
) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    async with (
        connect_databases(settings) as databases,
        connect_redis(settings) as redis,
    ):
        store = SessionStore(redis)
        provider = LatestRecommendations(databases.source, settings.database_timeout_seconds)
        availability_filter = partial(
            filter_available_items,
            databases.source,
            timeout_seconds=settings.database_timeout_seconds,
        )
        pagination = Pagination(
            store,
            provider,
            availability_filter,
            timeout_seconds=settings.recommendation_timeout_seconds,
        )
        async with _grpc_server(settings, pagination, redis, databases) as server:
            yield server


@asynccontextmanager
async def _grpc_server(
    settings: Settings,
    pagination: Pagination,
    redis: Redis,
    databases: Databases,
) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    server = grpc.aio.server()
    recommendation_service_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationService(pagination), server
    )
    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    health_task = None

    try:
        port = server.add_insecure_port(settings.grpc_bind_address)
        if not port:
            raise RuntimeError(f"Cannot bind gRPC server to {settings.grpc_bind_address}")
        await server.start()
        await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
        await health_service.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
        health_task = asyncio.create_task(
            _monitor_dependencies(settings, databases, redis, health_service)
        )
        yield server, port
    finally:
        await health_service.enter_graceful_shutdown()
        if health_task is not None:
            health_task.cancel()
            with suppress(asyncio.CancelledError):
                await health_task
        await server.stop(settings.shutdown_grace_seconds)


async def serve() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for signum in signals:
        loop.add_signal_handler(signum, stop.set)
    try:
        async with running_server(settings):
            logger.info("%s listening on %s", settings.app_name, settings.grpc_bind_address)
            await stop.wait()
    finally:
        for signum in signals:
            loop.remove_signal_handler(signum)


def main() -> None:
    configure_logging("recommendation-service")
    try:
        asyncio.run(serve())
    except Exception as exc:
        logger.error("Recommendation service stopped unexpectedly", extra=error_fields(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
