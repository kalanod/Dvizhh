import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dvizh_backend.api.errors import register_error_handlers
from dvizh_backend.api.routers import (
    admin,
    discovery,
    events,
    friends,
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
from dvizh_backend.storage import MediaStorage

settings = get_settings()
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_service = DatabaseService(settings.database_url)
    app.state.database_service = database_service
    app.state.media_storage = MediaStorage(settings)
    try:
        await database_service.ping()
    except Exception as exc:
        if settings.require_database:
            await database_service.dispose()
            raise
        logger.warning("База данных недоступна: %s", exc)
    try:
        yield
    finally:
        await database_service.dispose()


app = FastAPI(
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
app.include_router(lifecycle.router)
app.include_router(media.router)
app.include_router(maps.router)
app.include_router(personal.router)
app.include_router(system.router)
register_error_handlers(app)
