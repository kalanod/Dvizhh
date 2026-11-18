import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from os import getenv

import uvicorn
from dvizh_logging import error_fields
from dvizh_logging.http import RequestLoggingMiddleware, configure_http_logging
from fastapi import FastAPI
from grpc import aio

from dvizh_backend.api.errors import register_error_handlers
from dvizh_backend.api.routers import (
    admin,
    discovery,
    events,
    friends,
    interactions,
    lifecycle,
    maps,
    media,
    personal,
    system,
    tags,
    users,
)
from dvizh_backend.api.routers import settings as settings_router
from dvizh_backend.config import get_settings
from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.services.recommendation_client import RecommendationClient
from dvizh_backend.services.recommendation_health import monitor_feed_outcomes
from dvizh_backend.storage import MediaStorage

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_service = DatabaseService(settings.database_url)
    app.state.database_service = database_service
    app.state.media_storage = MediaStorage(settings)
    app.state.recommendation_client = None
    async with AsyncExitStack() as resources:
        resources.push_async_callback(database_service.dispose)
        if settings.recommendation_grpc_address:
            channel = await resources.enter_async_context(
                aio.insecure_channel(settings.recommendation_grpc_address)
            )
            app.state.recommendation_client = RecommendationClient(
                channel, timeout_seconds=settings.recommendation_grpc_timeout_seconds
            )
        try:
            await database_service.ping()
        except Exception as exc:
            if settings.require_database:
                raise
            logger.warning(
                "Database unavailable", extra={"dependency": "postgresql", **error_fields(exc)}
            )
        if getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
            await resources.enter_async_context(monitor_feed_outcomes(database_service))
        yield


class Application(FastAPI):
    def build_middleware_stack(self) -> RequestLoggingMiddleware:
        return RequestLoggingMiddleware(super().build_middleware_stack())


app = Application(
    title=settings.app_name,
    description="API персонализированной афиши событий: пользователи, события и участие в них.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(admin.router)
app.include_router(settings_router.router)
app.include_router(tags.router)
app.include_router(users.router)
app.include_router(friends.router)
app.include_router(discovery.router)
app.include_router(events.router)
app.include_router(interactions.router)
app.include_router(lifecycle.router)
app.include_router(media.router)
app.include_router(maps.router)
app.include_router(personal.router)
app.include_router(system.router)
register_error_handlers(app)


if __name__ == "__main__":
    configure_http_logging("backend")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None, access_log=False)
