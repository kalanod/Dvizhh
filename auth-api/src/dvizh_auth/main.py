from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dvizh_auth.api.errors import register_error_handlers
from dvizh_auth.api.routers import auth, system
from dvizh_auth.config import get_settings
from dvizh_auth.database import Database

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(get_settings().database_url)
    try:
        if settings.require_database:
            await database.ping()
        app.state.database = database
        yield
    finally:
        await database.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(system.router)
app.include_router(auth.router)
register_error_handlers(app)
