import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .db import engine
from .models import Base
from .routers import events, friends, users

settings = get_settings()
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception as exc:
        if settings.require_database:
            raise
        logger.warning("База данных недоступна, таблицы не созданы: %s", exc)
    yield
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
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/api", tags=["system"], summary="Проверка, что API запущен.")
async def root() -> dict[str, str]:
    return {"message": "Dvizh API is running"}
