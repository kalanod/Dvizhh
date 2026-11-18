import asyncio
import logging
from datetime import datetime

import asyncpg
from dvizh_logging.windows import reporting_minutes

from .database import Databases

logger = logging.getLogger(__name__)
_IMPRESSIONS = """
    SELECT user_id, session_id, request_id, item_id, occurrence_id
    FROM public.recsys_attributed_impressions
    WHERE received_at >= $1 AND received_at < $2
"""
_MATCHED = """
    SELECT count(*)
    FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[])
        AS impression(user_id, session_id, request_id, item_id, occurrence_id)
    JOIN public.recommendation_pages AS page
        ON (page.request_id, page.session_id, page.user_id) =
            (impression.request_id, impression.session_id, impression.user_id)
    WHERE EXISTS (
        SELECT FROM jsonb_array_elements(page.items) AS item
        WHERE item->>'item_id' = impression.item_id
          AND (impression.occurrence_id IS NULL
               OR item->>'occurrence_id' = impression.occurrence_id)
    )
"""


async def measure_feedback(
    source: asyncpg.Connection, journal: asyncpg.Connection, start: datetime, end: datetime,
) -> dict[str, int]:
    attributed = matched = 0
    async with source.transaction(isolation="repeatable_read", readonly=True):
        cursor = await source.cursor(_IMPRESSIONS, start, end)
        while batch := await cursor.fetch(1000):
            attributed += len(batch)
            matched += await journal.fetchval(_MATCHED, *zip(*batch, strict=True))
    return {
        "attributed_impressions": attributed,
        "matched_impressions": matched,
    }


async def monitor_feedback(databases: Databases, timeout_seconds: float) -> None:
    async for start, end in reporting_minutes():
        try:
            async with (
                asyncio.timeout(timeout_seconds),
                databases.source.acquire() as source,
                databases.vector.acquire() as journal,
            ):
                counts = await measure_feedback(source, journal, start, end)
            logger.info(
                "Recommendation data health",
                extra={"operation": "recsys.feedback_health", **counts},
            )
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError) as error:
            logger.warning(
                "Recommendation feedback check failed",
                extra={"operation": "recsys.feedback_health", "error_type": type(error).__name__},
            )
