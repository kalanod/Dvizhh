import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .config import get_settings
from .database.database_service import DatabaseService
from .db import engine
from .routers import events, friends, users

settings = get_settings()
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_service = DatabaseService(settings.database_url)
    app.state.database_service = database_service
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
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="API персонализированной афиши событий: пользователи, события и участие в них.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(users.router)
app.include_router(friends.router)
app.include_router(events.router)


@app.get(
    "/api/health",
    tags=["system"],
    summary="Состояние сервиса (используется healthcheck-ом контейнера).",
)
async def health(request: Request) -> dict[str, str]:
    database_service: DatabaseService = request.app.state.database_service
    await database_service.ping()
    return {"status": "ok", "service": "backend", "database": "ok"}


@app.get("/api", tags=["system"], summary="Проверка, что API запущен.")
async def root() -> dict[str, str]:
    return {"message": "Dvizh API is running"}
