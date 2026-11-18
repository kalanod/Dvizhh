import asyncio
import logging
from datetime import datetime

from dvizh_logging.windows import reporting_minutes
from sqlalchemy import Text, bindparam, column, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from .database import Databases, read_snapshot
from .feedback_tables import recommendation_pages, recsys_attributed_impressions

logger = logging.getLogger(__name__)


async def measure_feedback(
    source: AsyncConnection,
    journal: AsyncConnection,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    impression = recsys_attributed_impressions.c
    keys = ("user_id", "session_id", "request_id", "item_id", "occurrence_id")
    statement = select(*(impression[key] for key in keys)).where(
        impression.received_at >= start,
        impression.received_at < end,
    )
    page = recommendation_pages.c
    item = func.jsonb_array_elements(page["items"]).table_valued(column("value", JSONB))
    shown = (
        func.unnest(*(bindparam(key, type_=ARRAY(Text)) for key in keys))
        .table_valued(*keys)
        .render_derived(name="shown")
    )
    on_page = (
        select(1)
        .select_from(item)
        .where(
            item.c.value["item_id"].astext == shown.c.item_id,
            or_(
                shown.c.occurrence_id.is_(None),
                item.c.value["occurrence_id"].astext == shown.c.occurrence_id,
            ),
        )
        .correlate(shown, recommendation_pages)
        .exists()
    )
    matched_count = (
        select(func.count())
        .join_from(
            shown,
            recommendation_pages,
            (page.request_id == shown.c.request_id)
            & (page.session_id == shown.c.session_id)
            & (page.user_id == shown.c.user_id),
        )
        .where(on_page)
    )
    attributed = matched = 0
    async with (
        read_snapshot(source),
        source.stream(statement.execution_options(yield_per=1000)) as rows,
    ):
        async for batch in rows.partitions(1000):
            attributed += len(batch)
            columns = dict(zip(keys, zip(*batch, strict=True), strict=True))
            matched += await journal.scalar(matched_count, columns)
    return {"attributed_impressions": attributed, "matched_impressions": matched}


async def monitor_feedback(databases: Databases, timeout_seconds: float) -> None:
    async for start, end in reporting_minutes():
        try:
            async with (
                asyncio.timeout(timeout_seconds),
                databases.source.connect() as source,
                databases.vector.connect() as journal,
            ):
                counts = await measure_feedback(source, journal, start, end)
            logger.info(
                "Recommendation data health",
                extra={"operation": "recsys.feedback_health", **counts},
            )
        except (SQLAlchemyError, OSError, TimeoutError) as error:
            logger.warning(
                "Recommendation feedback check failed",
                extra={"operation": "recsys.feedback_health", "error_type": type(error).__name__},
            )
