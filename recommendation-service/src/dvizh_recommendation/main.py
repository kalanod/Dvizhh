import asyncio
import logging
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from .config import Settings, get_settings
from .database import connect_databases
from .generated import recommendation_service_pb2_grpc
from .service import SERVICE_NAME, RecommendationService


@asynccontextmanager
async def running_server(settings: Settings) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    async with connect_databases(settings), _grpc_server(settings) as server:
        yield server


@asynccontextmanager
async def _grpc_server(settings: Settings) -> AsyncIterator[tuple[grpc.aio.Server, int]]:
    server = grpc.aio.server()
    recommendation_service_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationService(), server
    )
    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)

    try:
        port = server.add_insecure_port(settings.grpc_bind_address)
        if not port:
            raise RuntimeError(f"Cannot bind gRPC server to {settings.grpc_bind_address}")
        await server.start()
        await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
        await health_service.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
        yield server, port
    finally:
        await health_service.enter_graceful_shutdown()
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
            logging.info("%s listening on %s", settings.app_name, settings.grpc_bind_address)
            await stop.wait()
    finally:
        for signum in signals:
            loop.remove_signal_handler(signum)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
