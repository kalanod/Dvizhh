from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from ..catalog import AVAILABLE_ITEMS_CONDITION
from ..recommendations import RecommendationQuery
from .base import Ranker

# $1 limit, $2 excluded IDs, $3 viewer; strategy parameters start after them.
_FIRST_ORDER_PARAMETER = 4


@dataclass(frozen=True)
class SqlOrder:
    """Sort keys a strategy adds to the shared candidate query.

    ``expression`` is the ORDER BY list without the final tie-breaker and refers to
    its own parameters as ``{0}``, ``{1}``, ... in the order of ``params``.
    ``joins`` may add one-to-one joins (for example, the event location).
    Values coming from a request are always passed as ``params``, never as text.
    """

    expression: str
    params: tuple[object, ...] = ()
    joins: str = ""


class SqlRanker(Ranker):
    """Ranking executed by PostgreSQL: ``ORDER BY ... LIMIT n``.

    The database never sorts the whole catalog for a page: with ``LIMIT`` it keeps
    only the best ``n`` rows (top-N heap sort, O(M log n)), and with a matching
    index it reads them in order without sorting at all. Only ``n + 1`` IDs leave
    the database.

    The base query keeps the shared rules in one place: catalog availability,
    excluded IDs, events the viewer marked "not interested" and the final
    ``e.id DESC`` tie-breaker that makes the order deterministic.
    """

    def __init__(self, pool: asyncpg.Pool, timeout_seconds: float = 5) -> None:
        self.pool = pool
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def order(self, query: RecommendationQuery, connection: asyncpg.Connection) -> SqlOrder:
        """Sort keys for this request; may read user data through ``connection``."""

    async def _rank(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> Sequence[str]:
        excluded = [UUID(item_id) for item_id in exclude_ids]
        async with self.pool.acquire(timeout=self.timeout_seconds) as connection:
            order = await self.order(query, connection)
            rows = await connection.fetch(
                self._statement(order),
                limit,
                excluded,
                viewer_uuid(query.user_id),
                *order.params,
                timeout=self.timeout_seconds,
            )
        return [str(row["id"]) for row in rows]

    @staticmethod
    def _statement(order: SqlOrder) -> str:
        placeholders = [f"${_FIRST_ORDER_PARAMETER + index}" for index in range(len(order.params))]
        return f"""
SELECT e.id
FROM events AS e
{order.joins}
WHERE {AVAILABLE_ITEMS_CONDITION}
    AND NOT (e.id = ANY($2::uuid[]))
    AND NOT EXISTS (
        SELECT 1
        FROM event_dismissals AS d
        WHERE d.event_id = e.id
          AND d.user_id = $3::uuid
    )
ORDER BY
    {order.expression.format(*placeholders)},
    e.id DESC
LIMIT $1;
"""


def viewer_uuid(user_id: str) -> UUID | None:
    """Profile ID of the viewer, or None when the ID is not a profile UUID."""
    try:
        return UUID(user_id)
    except ValueError:
        return None