import math
from collections.abc import Mapping
from typing import ClassVar

import asyncpg

from ..recommendations import RecommendationQuery
from .base import InvalidRankingRequest
from .sql import SqlOrder, SqlRanker, viewer_uuid


class NoveltyRanker(SqlRanker):
    """Most recently published first. Not personalized."""

    name = "novelty"

    async def order(self, query: RecommendationQuery, connection: asyncpg.Connection) -> SqlOrder:
        return SqlOrder("e.published_at DESC NULLS LAST")


class TitleRanker(SqlRanker):
    """Alphabetical by title, case-insensitive. Not personalized."""

    name = "title"

    async def order(self, query: RecommendationQuery, connection: asyncpg.Connection) -> SqlOrder:
        return SqlOrder("lower(e.title) ASC, e.title ASC")


class DistanceRanker(SqlRanker):
    """Nearest first by great-circle distance to the viewer.

    The point is ``context.latitude/longitude`` (current geolocation) or, when the
    request has neither, the location saved in the viewer's profile.
    Events without coordinates (online) go after all located events.
    """

    name = "distance"
    EARTH_RADIUS_KM: ClassVar[float] = 6371.0088

    async def order(self, query: RecommendationQuery, connection: asyncpg.Connection) -> SqlOrder:
        latitude, longitude = await self._origin(query, connection)
        # Haversine; LEAST guards asin against rounding slightly above 1.
        distance = f"""
            ({self.EARTH_RADIUS_KM} * 2 * asin(LEAST(1, sqrt(
                power(sin(radians(l.latitude::float8 - {{0}}::float8) / 2), 2)
                + cos(radians({{0}}::float8)) * cos(radians(l.latitude::float8))
                * power(sin(radians(l.longitude::float8 - {{1}}::float8) / 2), 2)
            ))))"""
        return SqlOrder(
            expression=f"{distance} ASC NULLS LAST",
            params=(latitude, longitude),
            joins="LEFT JOIN locations AS l ON l.id = e.location_id",
        )

    async def _origin(
        self, query: RecommendationQuery, connection: asyncpg.Connection
    ) -> tuple[float, float]:
        if "latitude" in query.context or "longitude" in query.context:
            return (
                _coordinate(query.context, "latitude", 90),
                _coordinate(query.context, "longitude", 180),
            )
        user_id = viewer_uuid(query.user_id)
        row = None
        if user_id is not None:
            row = await connection.fetchrow(
                "SELECT latitude, longitude FROM profiles WHERE id = $1 AND deleted_at IS NULL",
                user_id,
                timeout=self.timeout_seconds,
            )
        if row is None or row["latitude"] is None or row["longitude"] is None:
            raise InvalidRankingRequest(
                "Ranking 'distance' requires context.latitude and context.longitude "
                "or a location in the user profile"
            )
        return float(row["latitude"]), float(row["longitude"])

class RelevanceRanker(SqlRanker):
    """Personal relevance: interest in the event's tags, popularity and freshness.

    The user profile is a weight per tag built from the user's own signals
    (favorites, participation, "not interested", opens and clicks), each decayed
    with a half-life so recent behaviour matters more. An event scores::

        W_INTEREST  * sum(tag interest) / sqrt(event tag count)
      + W_POPULAR   * ln(1 + going participants)
      + W_FRESHNESS * 2^(-age / FRESHNESS_HALF_LIFE)

    Without user signals only popularity and freshness remain; that is a
    fallback, not personalization.
    """

    name = "relevance"

    SIGNAL_WEIGHTS: ClassVar[Mapping[str, float]] = {
        "PARTICIPATION_GOING": 4.0,
        "PARTICIPATION_REQUESTED": 3.0,
        "FAVORITE": 3.0,
        "INTERACTION_JOIN_CLICK": 2.0,
        "INTERACTION_EXTERNAL_LINK_CLICK": 2.0,
        "INTERACTION_OPEN": 1.0,
        "PARTICIPATION_CANCELLED": -1.0,
        "DISMISSED": -4.0,
    }
    SIGNAL_HALF_LIFE_DAYS: ClassVar[float] = 30
    SIGNAL_WINDOW_DAYS: ClassVar[int] = 180
    PROFILE_TAG_LIMIT: ClassVar[int] = 50
    W_INTEREST: ClassVar[float] = 1.0
    W_POPULAR: ClassVar[float] = 0.15
    W_FRESHNESS: ClassVar[float] = 0.3
    FRESHNESS_HALF_LIFE_DAYS: ClassVar[float] = 14

    PROFILE_QUERY: ClassVar[str] = """
WITH signals (event_id, kind, happened_at) AS (
    SELECT f.event_id, 'FAVORITE', f.created_at
    FROM event_favorites AS f
    WHERE f.user_id = $1
    UNION ALL
    SELECT o.event_id, 'PARTICIPATION_' || p.status::text, p.updated_at
    FROM event_participations AS p
    JOIN event_occurrences AS o ON o.id = p.occurrence_id
    WHERE p.user_id = $1
    UNION ALL
    SELECT d.event_id, 'DISMISSED', d.created_at
    FROM event_dismissals AS d
    WHERE d.user_id = $1
    UNION ALL
    SELECT i.event_id, 'INTERACTION_' || i.type::text, i.occurred_at
    FROM event_interactions AS i
    WHERE i.user_id = $1
      AND i.occurred_at > NOW() - make_interval(days => $4)
),
interest AS (
    SELECT
        t.tag_id,
        SUM(
            w.weight * exp(
                -ln(2) * GREATEST(EXTRACT(EPOCH FROM NOW() - s.happened_at), 0) / $5
            )
        ) AS weight
    FROM signals AS s
    JOIN unnest($2::text[], $3::float8[]) AS w (kind, weight) ON w.kind = s.kind
    JOIN event_tags AS t ON t.event_id = s.event_id
    GROUP BY t.tag_id
)
SELECT tag_id, weight
FROM interest
WHERE weight <> 0
ORDER BY abs(weight) DESC, tag_id
LIMIT $6;
"""

    async def order(self, query: RecommendationQuery, connection: asyncpg.Connection) -> SqlOrder:
        tag_ids, weights = await self._interest_profile(query, connection)
        score = """(
            {2}::float8 * COALESCE((
                SELECT SUM(interest.weight) / sqrt(COUNT(*))
                FROM event_tags AS et
                LEFT JOIN unnest({0}::uuid[], {1}::float8[]) AS interest (tag_id, weight)
                    ON interest.tag_id = et.tag_id
                WHERE et.event_id = e.id
            ), 0)
            + {3}::float8 * ln(1 + (
                SELECT COUNT(*)
                FROM event_participations AS p
                JOIN event_occurrences AS po ON po.id = p.occurrence_id
                WHERE po.event_id = e.id
                  AND p.status = 'GOING'
            ))
            + {4}::float8 * exp(
                -ln(2) * GREATEST(
                    EXTRACT(EPOCH FROM NOW() - COALESCE(e.published_at, e.created_at)), 0
                ) / {5}::float8
            )
        )"""
        return SqlOrder(
            expression=f"{score} DESC, e.published_at DESC NULLS LAST",
            params=(
                tag_ids,
                weights,
                self.W_INTEREST,
                self.W_POPULAR,
                self.W_FRESHNESS,
                self.FRESHNESS_HALF_LIFE_DAYS * 86400,
            ),
        )

    async def _interest_profile(
        self, query: RecommendationQuery, connection: asyncpg.Connection
    ) -> tuple[list, list[float]]:
        """Tag weights normalized to [-1, 1]; empty for users without signals."""
        user_id = viewer_uuid(query.user_id)
        if user_id is None:
            return [], []
        rows = await connection.fetch(
            self.PROFILE_QUERY,
            user_id,
            list(self.SIGNAL_WEIGHTS),
            list(self.SIGNAL_WEIGHTS.values()),
            self.SIGNAL_WINDOW_DAYS,
            self.SIGNAL_HALF_LIFE_DAYS * 86400,
            self.PROFILE_TAG_LIMIT,
            timeout=self.timeout_seconds,
        )
        if not rows:
            return [], []
        scale = max(abs(row["weight"]) for row in rows)
        return [row["tag_id"] for row in rows], [row["weight"] / scale for row in rows]


def _coordinate(context: Mapping[str, object], key: str, bound: float) -> float:
    value = context.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or abs(value) > bound
    ):
        raise InvalidRankingRequest(
            f"Ranking 'distance' requires context.{key} between {-bound} and {bound}"
        )
    return float(value)