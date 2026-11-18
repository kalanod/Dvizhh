import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Self
from uuid import UUID

import asyncpg
from dvizh_logging import log_dependency
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .recommendations import FeatureSnapshot, InvalidRequest, RecommendationQuery


class Viewport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    west: Annotated[float, Field(ge=-180, le=180)]
    south: Annotated[float, Field(ge=-90, le=90)]
    east: Annotated[float, Field(ge=-180, le=180)]
    north: Annotated[float, Field(ge=-90, le=90)]

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.south >= self.north or self.west == self.east:
            raise ValueError("Viewport must have a positive area")
        return self


class CatalogFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    q: Annotated[str, Field(max_length=500)] = ""
    tag_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    free_only: bool = False
    available_only: bool = False
    viewport: Viewport | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Invalid date range")
        return self

    @classmethod
    def from_query(cls, query: RecommendationQuery) -> Self:
        if query.filters.keys() - cls.model_fields.keys():
            raise NotImplementedError("Unsupported filters")
        try:
            return cls.model_validate_json(json.dumps(dict(query.filters), allow_nan=False))
        except (ValidationError, ValueError, TypeError) as exc:
            raise InvalidRequest("Invalid recommendations filters") from exc


_ELIGIBLE = """
    (
        COALESCE(c.ends_at, c.starts_at) >= $1
        OR (c.is_all_day AND (c.starts_at AT TIME ZONE c.timezone)::date
            = ($1::timestamptz AT TIME ZONE c.timezone)::date)
    )
"""

_CATALOG_QUERY = f"""
WITH matching AS (
    SELECT DISTINCT ON (c.item_id)
        c.item_id, c.occurrence_id, c.starts_at, c.participants_count,
        c.published_at, c.created_at, c.price_type, c.format, c.join_policy
    FROM public.recsys_catalog AS c
    WHERE {_ELIGIBLE}
        AND ($2::uuid[] IS NULL OR c.item_id = ANY($2))
        AND ($17::uuid[] IS NULL OR EXISTS (
            SELECT 1
            FROM unnest($2::uuid[], $17) AS requested(item_id, occurrence_id)
            WHERE requested.item_id = c.item_id
              AND (requested.occurrence_id IS NULL OR requested.occurrence_id = c.occurrence_id)
        ))
        AND NOT (c.item_id = ANY($3::uuid[]))
        AND NOT EXISTS (
            SELECT 1 FROM public.recsys_dismissals AS d
            WHERE d.user_id = $4::uuid AND d.item_id = c.item_id
        )
        AND ($5::uuid IS NULL OR $5 = ANY(c.topic_ids))
        AND ($6::date IS NULL
            OR (COALESCE(c.ends_at, c.starts_at) AT TIME ZONE c.timezone)::date >= $6)
        AND ($7::date IS NULL OR (c.starts_at AT TIME ZONE c.timezone)::date <= $7)
        AND (NOT $8::bool OR c.price_type = 'FREE')
        AND (NOT $9::bool OR c.capacity IS NULL OR c.participants_count < c.capacity)
        AND ($10::text = '' OR CASE WHEN $11::text IS NULL
            THEN c.search_document @@ websearch_to_tsquery('russian', $10)
            ELSE c.title ~* $11
        END)
        AND ($12::double precision IS NULL OR (
            c.latitude BETWEEN $13::double precision AND $14::double precision
            AND CASE WHEN $12 <= $15::double precision THEN c.longitude BETWEEN $12 AND $15
                ELSE c.longitude >= $12 OR c.longitude <= $15 END
        ))
    ORDER BY c.item_id, (c.starts_at <= $1) DESC, c.starts_at, c.occurrence_id
)
SELECT *
FROM matching
ORDER BY published_at DESC NULLS LAST, item_id DESC
LIMIT $16
"""


async def catalog_items(
    pool: asyncpg.Pool,
    filters: CatalogFilters,
    *,
    as_of: datetime,
    user_id: UUID | None = None,
    requested_occurrences: Mapping[UUID, UUID | None] | None = None,
    exclude_ids: Sequence[UUID] = (),
    limit: int | None = None,
    timeout_seconds: float = 5,
) -> list[asyncpg.Record]:
    viewport = filters.viewport
    text = filters.q.strip()
    hashtag = None
    if re.fullmatch(r"#\w+", text):
        hashtag = rf"(^|[^[:alnum:]_#]){text}($|[^[:alnum:]_])"
    operation = "get_candidates" if requested_occurrences is None else "filter_available_items"
    with log_dependency("postgres", operation):
        async with pool.acquire(timeout=timeout_seconds) as connection:
            return await connection.fetch(
                _CATALOG_QUERY,
                as_of,
                None if requested_occurrences is None else list(requested_occurrences),
                list(exclude_ids),
                user_id,
                filters.tag_id,
                filters.date_from,
                filters.date_to,
                filters.free_only,
                filters.available_only,
                text,
                hashtag,
                viewport.west if viewport else None,
                viewport.south if viewport else None,
                viewport.north if viewport else None,
                viewport.east if viewport else None,
                limit,
                None if requested_occurrences is None else list(requested_occurrences.values()),
                timeout=timeout_seconds,
            )


async def filter_available_items(
    pool: asyncpg.Pool,
    item_ids: Sequence[str],
    query: RecommendationQuery | None = None,
    snapshots: Sequence[FeatureSnapshot | None] = (),
    *,
    timeout_seconds: float = 5,
) -> tuple[str, ...]:
    if not item_ids:
        return ()
    ids = map(UUID, item_ids)
    requested_occurrences = (
        dict(
            zip(
                ids,
                (snapshot.occurrence_id if snapshot else None for snapshot in snapshots),
                strict=True,
            )
        )
        if snapshots
        else dict.fromkeys(ids)
    )
    rows = await catalog_items(
        pool,
        CatalogFilters.from_query(query) if query else CatalogFilters(),
        as_of=datetime.now(UTC),
        user_id=query.viewer_id if query else None,
        requested_occurrences=requested_occurrences,
        timeout_seconds=timeout_seconds,
    )
    available = {str(row["item_id"]) for row in rows}
    return tuple(item_id for item_id in item_ids if item_id in available)
