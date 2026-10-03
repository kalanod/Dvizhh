from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .config import get_settings
from .database.database_service import DatabaseService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_service = DatabaseService(settings.database_url)
    await database_service.ping()
    app.state.database_service = database_service
    try:
        yield
    finally:
        await database_service.dispose()


app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health", tags=["system"])
async def health(request: Request) -> dict[str, str]:
    database_service: DatabaseService = request.app.state.database_service
    await database_service.ping()
    return {"status": "ok", "service": "backend", "database": "ok"}


@app.get("/api", tags=["system"])
async def root() -> dict[str, str]:
    return {"message": "Dvizh API is running"}
