from sqlalchemy import BigInteger, Column, DateTime, MetaData, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

_metadata = MetaData(schema="public")
_timestamp = DateTime(timezone=True)

recommendation_pages = Table(
    "recommendation_pages",
    _metadata,
    Column("request_id", Text),
    Column("session_id", Text),
    Column("user_id", Text),
    Column("parameters_hash", Text),
    Column("served_at", _timestamp),
    Column("items", JSONB),
)
recsys_interactions = Table(
    "recsys_interactions",
    _metadata,
    Column("user_id", Uuid),
    Column("item_id", Uuid),
    Column("occurrence_id", Uuid),
    Column("event_type", Text),
    Column("occurred_at", _timestamp),
    Column("received_at", _timestamp),
    Column("interaction_id", Uuid),
    Column("session_id", Uuid),
    Column("request_id", Uuid),
)
recsys_confirmed_registrations = Table(
    "recsys_confirmed_registrations",
    _metadata,
    Column("user_id", Uuid),
    Column("item_id", Uuid),
    Column("occurrence_id", Uuid),
    Column("confirmed_at", _timestamp),
    Column("origin_interaction_id", Uuid),
)
recsys_participation_history = Table(
    "recsys_participation_history",
    _metadata,
    Column("user_id", Uuid),
    Column("occurrence_id", Uuid),
    Column("status", Text),
    Column("changed_at", _timestamp),
    Column("change_id", BigInteger),
)
recsys_attributed_impressions = Table(
    "recsys_attributed_impressions",
    _metadata,
    Column("user_id", Text),
    Column("session_id", Text),
    Column("request_id", Text),
    Column("item_id", Text),
    Column("occurrence_id", Text),
    Column("received_at", _timestamp),
)
recsys_encoder_items = Table(
    "recsys_encoder_items",
    _metadata,
    Column("item_id", Uuid),
    Column("title", Text),
    Column("description", Text),
    Column("topic_ids", ARRAY(Uuid)),
)
