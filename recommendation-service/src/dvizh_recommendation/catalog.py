from collections.abc import Sequence
from uuid import UUID

import asyncpg
from dvizh_logging import log_dependency

AVAILABLE_ITEMS_QUERY = """
SELECT e.id
FROM events AS e
WHERE e.status = 'PUBLISHED'
    AND e.visibility = 'PUBLIC'
    AND e.deleted_at IS NULL
    AND EXISTS (
        SELECT 1
        FROM event_occurrences AS o
        WHERE o.event_id = e.id
          AND o.status = 'SCHEDULED'
          AND (
              o.ends_at > NOW()
              OR (
                  o.ends_at IS NULL
                  AND o.starts_at >= NOW()
              )
          )
    )
"""


async def filter_available_items(
    pool: asyncpg.Pool,
    item_ids: Sequence[str],
    *,
    timeout_seconds: float = 5,
) -> tuple[str, ...]:
    if not item_ids:
        return ()
    with log_dependency("postgres", "filter_available_items"):
        async with pool.acquire(timeout=timeout_seconds) as connection:
            rows = await connection.fetch(
                AVAILABLE_ITEMS_QUERY + " AND e.id = ANY($1::uuid[])",
                [UUID(item_id) for item_id in item_ids],
                timeout=timeout_seconds,
            )
    available = {str(row["id"]) for row in rows}
    return tuple(item_id for item_id in item_ids if item_id in available)
