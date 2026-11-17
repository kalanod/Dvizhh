from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from dvizh_logging.http import RequestLoggingMiddleware, configure_http_logging
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


class Application(FastAPI):
    def build_middleware_stack(self) -> RequestLoggingMiddleware:
        return RequestLoggingMiddleware(super().build_middleware_stack())


app = Application(title=settings.app_name, lifespan=lifespan)

app.include_router(system.router)
app.include_router(auth.router)
register_error_handlers(app)


if __name__ == "__main__":
    configure_http_logging("auth-api")
    uvicorn.run(app, host="0.0.0.0", port=8003, log_config=None, access_log=False)
