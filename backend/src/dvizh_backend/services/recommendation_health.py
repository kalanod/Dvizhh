import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime

from dvizh_logging.windows import reporting_minutes
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.database.models import DiscoveryPage

logger = logging.getLogger(__name__)


async def measure_feed_outcomes(
    session: AsyncSession, start: datetime, end: datetime,
) -> dict[str, int]:
    statement = select(
        func.count().label("total_pages"),
        func.count().filter(DiscoveryPage.request_id.is_(None)).label("fallback_pages"),
    ).where(DiscoveryPage.served_at >= start, DiscoveryPage.served_at < end)
    return dict((await session.execute(statement)).mappings().one())


async def _report_pages(database: DatabaseService) -> None:
    async for start, end in reporting_minutes():
        try:
            async with asyncio.timeout(5), database.session() as session:
                counts = await measure_feed_outcomes(session, start, end)
            logger.info(
                "Recommendation page health",
                extra={"operation": "recsys.feedback_health", **counts},
            )
        except (SQLAlchemyError, OSError, TimeoutError) as error:
            logger.warning(
                "Recommendation page check failed",
                extra={"operation": "recsys.feedback_health", "error_type": type(error).__name__},
            )


@asynccontextmanager
async def monitor_feed_outcomes(database: DatabaseService) -> AsyncIterator[None]:
    task = asyncio.create_task(_report_pages(database))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
