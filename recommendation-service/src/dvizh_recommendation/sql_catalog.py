from datetime import datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.sql import ColumnElement, FromClause

_metadata = sa.MetaData(schema="public")
_timestamp = sa.DateTime(timezone=True)

recsys_catalog = sa.Table(
    "recsys_catalog",
    _metadata,
    sa.Column("item_id", sa.Uuid),
    sa.Column("occurrence_id", sa.Uuid),
    sa.Column("title", sa.Text),
    sa.Column("description", sa.Text),
    sa.Column("search_document", TSVECTOR),
    sa.Column("published_at", _timestamp),
    sa.Column("created_at", _timestamp),
    sa.Column("source_updated_at", _timestamp),
    sa.Column("starts_at", _timestamp),
    sa.Column("ends_at", _timestamp),
    sa.Column("timezone", sa.Text),
    sa.Column("is_all_day", sa.Boolean),
    sa.Column("capacity", sa.Integer),
    sa.Column("participants_count", sa.BigInteger),
    sa.Column("price_type", sa.Text),
    sa.Column("format", sa.Text),
    sa.Column("join_policy", sa.Text),
    sa.Column("city", sa.Text),
    sa.Column("latitude", sa.Double),
    sa.Column("longitude", sa.Double),
    sa.Column("topic_ids", ARRAY(sa.Uuid)),
)
recsys_dismissals = sa.Table(
    "recsys_dismissals",
    _metadata,
    sa.Column("user_id", sa.Uuid),
    sa.Column("item_id", sa.Uuid),
)
event_embeddings = sa.Table(
    "event_embeddings",
    _metadata,
    sa.Column("event_id", sa.Uuid),
    sa.Column("model_name", sa.Text),
    sa.Column("embedding", Vector(384)),
    sa.Column("content_hash", sa.Text),
    sa.Column("is_candidate", sa.Boolean),
    sa.Column("source_updated_at", _timestamp),
    sa.Column("last_ends_at", _timestamp),
    sa.Column("next_starts_at", _timestamp),
    sa.Column("price_type", sa.Text),
    sa.Column("format", sa.Text),
    sa.Column("city", sa.Text),
    sa.Column("latitude", sa.Double),
    sa.Column("longitude", sa.Double),
    sa.Column("topic_ids", ARRAY(sa.Uuid)),
)
user_embeddings = sa.Table(
    "user_embeddings",
    _metadata,
    sa.Column("model_name", sa.Text),
    sa.Column("user_id", sa.Uuid),
    sa.Column("embedding", Vector(384)),
)
embedding_index_versions = sa.Table(
    "embedding_index_versions",
    _metadata,
    sa.Column("model_name", sa.Text),
    sa.Column("model_id", sa.Text),
    sa.Column("generated_at", _timestamp),
    sa.Column("artifact_sha256", sa.Text),
    sa.Column("dimension", sa.Integer),
    sa.Column("metric", sa.Text),
)


def local_date(timestamp: ColumnElement, timezone: ColumnElement) -> ColumnElement:
    return sa.cast(sa.func.timezone(timezone, timestamp), sa.Date)


def active_occurrence(
    table: FromClause,
    as_of: datetime,
    *,
    include_ending_now: bool = True,
) -> ColumnElement[bool]:
    c = table.c
    at = sa.literal(as_of, type_=_timestamp)
    ongoing = (
        sa.func.coalesce(c.ends_at, c.starts_at) >= at
        if include_ending_now
        else sa.or_(c.ends_at > at, sa.and_(c.ends_at.is_(None), c.starts_at >= at))
    )
    return sa.or_(
        ongoing,
        sa.and_(c.is_all_day, local_date(c.starts_at, c.timezone) == local_date(at, c.timezone)),
    )
