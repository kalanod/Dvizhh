from uuid import UUID

import asyncpg

# Выбирает опубликованные публичные мероприятия без soft delete,
# у которых существует допустимое проведение.
CANDIDATES_QUERY = """
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
ORDER BY
    e.published_at DESC NULLS LAST,
    e.id DESC
LIMIT $1;
"""


async def get_candidates(
    pool: asyncpg.Pool,
    limit: int = 20,
) -> list[UUID]:
    if type(limit) is not int:
        raise TypeError("limit must be an integer")

    if limit <= 0:
        raise ValueError("limit must be positive")

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            CANDIDATES_QUERY,
            limit,
        )

    return [row["id"] for row in rows]