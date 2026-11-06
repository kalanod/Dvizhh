from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .database import Database

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    database = Database(get_settings().database_url)
    try:
        if settings.require_database:
            await database.ping()
        app.state.database = database
        yield
    finally:
        await database.dispose()
        
        
app = FastAPI(title=settings.app_name, lifespan=lifespan)

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-api"}