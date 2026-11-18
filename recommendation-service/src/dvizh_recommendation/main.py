import asyncio
import json
import logging
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from os import getenv

import grpc
from dvizh_logging import configure_logging, error_fields
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from redis.asyncio import Redis

from .candidates import LatestRecommendations
from .catalog import filter_available_items
from .config import Settings, get_settings
from .database import Databases, connect_databases
from .feedback_health import monitor_feedback
from .generated import recommendation_service_pb2_grpc
from .hnsw import HnswCandidates
from .journal import RecommendationJournal
from .model_registry import load_ranker
from .pagination import Pagination, SessionStore
from .recommendations import BASELINE_VERSION, Ranker, RecommendationProvider
from .redis import connect_redis
from .service import SERVICE_NAME, RecommendationService

HEALTH_CHECK_INTERVAL_SECONDS = 5
logger = logging.getLogger(__name__)


async def _load_provider(
    databases: Databases,
    settings: Settings,
    ranker_uri: str | None,
    vector_model_id: str | None,
    *,
    vector_index_revision: str | None,
) -> LatestRecommendations:
    ranker = await load_ranker(ranker_uri, settings.ranker_model_dir) if ranker_uri else None
    if not vector_model_id:
        return LatestRecommendations(
            databases.source, settings.database_timeout_seconds, ranker=ranker
        )

    generator = HnswCandidates(databases.vector, vector_model_id, vector_index_revision or None)
    if not await generator.check_ready():
        raise ValueError("No compatible published HNSW index for the configured model")
    version = json.dumps(
        [ranker.version if ranker else BASELINE_VERSION, generator.model_id, generator.revision]
    )
    return LatestRecommendations(
        databases.source,
        settings.database_timeout_seconds,
        ranker=ranker,
        generators=(generator,),
        version=version,
    )


async def _update_readiness(
    settings: Settings,
    databases: Databases,
    redis: Redis,
    health_service: health.aio.HealthServicer,
    unavailable: set[str],
) -> None:
    results = await asyncio.gather(
        asyncio.wait_for(redis.ping(), timeout=settings.redis_timeout_seconds),
        asyncio.wait_for(
            databases.source.fetchval(
                "SELECT 1 FROM public.recsys_catalog CROSS JOIN public.recsys_dismissals LIMIT 0"
            ),
            timeout=settings.database_timeout_seconds,
        ),
        asyncio.wait_for(
            databases.vector.fetchval("SELECT 1 FROM public.recommendation_pages LIMIT 0"),
            timeout=settings.database_timeout_seconds,
        ),
        return_exceptions=True,
    )
    for dependency, result in zip(("redis", "postgres", "pgvector"), results, strict=True):
        if isinstance(result, BaseException) and dependency not in unavailable:
            logger.warning(
                "Dependency unavailable", extra={"dependency": dependency, **error_fields(result)}
            )
            unavailable.add(dependency)
        elif not isinstance(result, BaseException) and dependency in unavailable:
            logger.info("Dependency recovered", extra={"dependency": dependency})
            unavailable.remove(dependency)
    if unavailable:
        status = health_pb2.HealthCheckResponse.NOT_SERVING
    else:
        status = health_pb2.HealthCheckResponse.SERVING
    await health_service.set("", status)
    await health_service.set(SERVICE_NAME, status)


async def _monitor_dependencies(
    settings: Settings,
    databases: Databases,
    redis: Redis,
    health_service: health.aio.HealthServicer,
    unavailable: set[str],
) -> None:
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)
        await _update_readiness(settings, databases, redis, health_service, unavailable)


@asynccontextmanager
async def running_server(
    settings: Settings,
) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    async with (
        connect_databases(settings) as databases,
        connect_redis(settings) as redis,
    ):
        baseline = LatestRecommendations(databases.source, settings.database_timeout_seconds)
        provider = await _load_provider(
            databases,
            settings,
            settings.ranker_model_uri,
            settings.vector_model_id,
            vector_index_revision=settings.vector_index_revision,
        )
        previous_providers = {baseline.version: baseline}
        if settings.previous_ranker_model_uri or settings.previous_vector_model_id:
            previous_provider = await _load_provider(
                databases,
                settings,
                settings.previous_ranker_model_uri,
                settings.previous_vector_model_id,
                vector_index_revision=settings.previous_vector_index_revision,
            )
            previous_providers[previous_provider.version] = previous_provider

        vector_rankers: dict[tuple[str, str], Ranker | None] = {
            (
                candidate.ranker.version if candidate.ranker else BASELINE_VERSION,
                generator.model_id,
            ): candidate.ranker
            for candidate in (provider, *previous_providers.values())
            for generator in candidate.generators
            if isinstance(generator, HnswCandidates)
        }

        async def resolve_provider(version: str) -> RecommendationProvider | None:
            try:
                parts = json.loads(version)
            except ValueError:
                return None
            if (
                not isinstance(parts, list)
                or len(parts) not in (2, 3)
                or not all(isinstance(part, str) for part in parts)
            ):
                return None
            ranker_version, model_id, *revisions = parts
            key = (ranker_version, model_id)
            if key not in vector_rankers:
                return None
            revision = revisions[0] if revisions else model_id
            generator = HnswCandidates(databases.vector, model_id, revision)
            if not await generator.check_ready():
                return None
            return LatestRecommendations(
                databases.source,
                settings.database_timeout_seconds,
                ranker=vector_rankers[key],
                generators=(generator,),
                version=version,
            )

        store = SessionStore(redis, initial_version=provider.version)
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
            provider_version=provider.version,
            previous_providers=previous_providers,
            resolve_provider=resolve_provider,
        )
        journal = RecommendationJournal(
            databases.vector, timeout_seconds=settings.database_timeout_seconds
        )
        async with _grpc_server(settings, pagination, redis, databases, journal) as server:
            yield server


@asynccontextmanager
async def _grpc_server(
    settings: Settings,
    pagination: Pagination,
    redis: Redis,
    databases: Databases,
    journal: RecommendationJournal | None = None,
) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    server = grpc.aio.server()
    recommendation_service_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationService(
            pagination, journal, timeout_seconds=settings.recommendation_timeout_seconds
        ),
        server,
    )
    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    background_tasks: list[asyncio.Task[None]] = []
    unavailable: set[str] = set()

    try:
        port = server.add_insecure_port(settings.grpc_bind_address)
        if not port:
            raise RuntimeError(f"Cannot bind gRPC server to {settings.grpc_bind_address}")
        await _update_readiness(settings, databases, redis, health_service, unavailable)
        await server.start()
        background_tasks.append(asyncio.create_task(
            _monitor_dependencies(settings, databases, redis, health_service, unavailable)
        ))
        if getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
            background_tasks.append(asyncio.create_task(
                monitor_feedback(databases, settings.database_timeout_seconds)
            ))
        yield server, port
    finally:
        await health_service.enter_graceful_shutdown()
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
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
