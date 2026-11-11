import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dvizh_logging import error_fields
from dvizh_logging.sqlalchemy import trace_sqlalchemy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseService:
    """Own the SQLAlchemy engine and create request-scoped sessions."""

    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
        )
        trace_sqlalchemy(self.engine.sync_engine)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
                session.info.pop("rollback_callbacks", None)
            except BaseException:
                await session.rollback()
                for cleanup in session.info.pop("rollback_callbacks", []):
                    try:
                        await cleanup()
                    except Exception as exc:
                        logging.getLogger(__name__).error(
                            "Media rollback cleanup failed", extra=error_fields(exc)
                        )
                raise

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
