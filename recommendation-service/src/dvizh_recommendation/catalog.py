import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Self
from uuid import UUID

import sqlalchemy as sa
from dvizh_logging import log_dependency
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.dialects.postgresql import ARRAY, distinct_on
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from .recommendations import FeatureSnapshot, InvalidRequest, RecommendationQuery
from .sql_catalog import active_occurrence, local_date, recsys_catalog, recsys_dismissals


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


def _matching_items(
    filters: CatalogFilters,
    as_of: datetime,
    user_id: UUID | None,
    requested: Mapping[UUID, UUID | None] | None,
    exclude_ids: Sequence[UUID],
) -> sa.Subquery:
    c = recsys_catalog.c
    query = sa.select(
        c.item_id,
        c.occurrence_id,
        c.starts_at,
        c.participants_count,
        c.published_at,
        c.created_at,
        c.price_type,
        c.format,
        c.join_policy,
    ).where(active_occurrence(recsys_catalog, as_of))
    if requested is not None:
        ids = sa.literal(list(requested), ARRAY(sa.Uuid))
        if any(requested.values()):
            pairs = sa.func.unnest(ids, sa.literal(list(requested.values()), ARRAY(sa.Uuid)))
            pairs = pairs.table_valued(
                sa.column("item_id", sa.Uuid),
                sa.column("occurrence_id", sa.Uuid),
            ).render_derived(name="requested")
            query = query.join(
                pairs,
                sa.and_(
                    c.item_id == pairs.c.item_id,
                    sa.or_(
                        pairs.c.occurrence_id.is_(None), pairs.c.occurrence_id == c.occurrence_id
                    ),
                ),
            )
        else:
            query = query.where(c.item_id == sa.any_(ids))
    if exclude_ids:
        query = query.where(c.item_id != sa.all_(sa.literal(list(exclude_ids), ARRAY(sa.Uuid))))
    if user_id is not None:
        d = recsys_dismissals.c
        query = query.where(~sa.exists().where(d.user_id == user_id, d.item_id == c.item_id))
    if filters.tag_id is not None:
        query = query.where(filters.tag_id == sa.any_(c.topic_ids))
    if filters.date_from:
        end_date = local_date(sa.func.coalesce(c.ends_at, c.starts_at), c.timezone)
        query = query.where(end_date >= filters.date_from)
    if filters.date_to:
        query = query.where(local_date(c.starts_at, c.timezone) <= filters.date_to)
    if filters.free_only:
        query = query.where(c.price_type == "FREE")
    if filters.available_only:
        query = query.where(sa.or_(c.capacity.is_(None), c.participants_count < c.capacity))
    text = filters.q.strip()
    if re.fullmatch(r"#\w+", text):
        query = query.where(
            c.title.regexp_match(rf"(^|[^[:alnum:]_#]){text}($|[^[:alnum:]_])", flags="i")
        )
    elif text:
        query = query.where(
            c.search_document.bool_op("@@")(sa.func.websearch_to_tsquery("russian", text))
        )
    if viewport := filters.viewport:
        longitude = (
            c.longitude.between(viewport.west, viewport.east)
            if viewport.west <= viewport.east
            else sa.or_(c.longitude >= viewport.west, c.longitude <= viewport.east)
        )
        query = query.where(longitude, c.latitude.between(viewport.south, viewport.north))
    return (
        query.ext(distinct_on(c.item_id))
        .order_by(c.item_id, (c.starts_at <= as_of).desc(), c.starts_at, c.occurrence_id)
        .subquery("matching")
    )


async def catalog_items(
    pool: AsyncEngine,
    filters: CatalogFilters,
    *,
    as_of: datetime,
    user_id: UUID | None = None,
    requested_occurrences: Mapping[UUID, UUID | None] | None = None,
    exclude_ids: Sequence[UUID] = (),
    limit: int | None = None,
    timeout_seconds: float = 5,
) -> Sequence[RowMapping]:
    matching = _matching_items(filters, as_of, user_id, requested_occurrences, exclude_ids)
    query = (
        sa.select(matching)
        .order_by(
            matching.c.published_at.desc().nulls_last(),
            matching.c.item_id.desc(),
        )
        .limit(limit)
    )
    operation = "get_candidates" if requested_occurrences is None else "filter_available_items"
    with log_dependency("postgres", operation):
        async with asyncio.timeout(timeout_seconds), pool.connect() as connection:
            return (await connection.execute(query)).mappings().all()


async def filter_available_items(
    pool: AsyncEngine,
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
