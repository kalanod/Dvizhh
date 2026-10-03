from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .common import SoftDeleteMixin, TimestampMixin
from .enums import (
    EventFormat,
    EventJoinPolicy,
    EventManagerRole,
    EventOrigin,
    EventPriceType,
    EventStatus,
    EventVisibility,
    OccurrenceStatus,
)


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"
    __table_args__ = (
        Index("ix_topics_parent_sort_order", "parent_id", "sort_order"),
        Index("ix_topics_active_sort_order", "is_active", "sort_order"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL")
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        Index("ix_locations_city_region", "city", "region"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    address_line: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    external_place_id: Mapped[str | None] = mapped_column(String(255), index=True)


class Event(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity > 0", name="positive_capacity"),
        CheckConstraint(
            "(origin = 'USER' AND organizer_user_id IS NOT NULL "
            "AND organizer_organization_id IS NULL) OR "
            "(origin = 'ORGANIZATION' AND organizer_user_id IS NULL "
            "AND organizer_organization_id IS NOT NULL) OR "
            "(origin = 'EXTERNAL' AND organizer_user_id IS NULL)",
            name="organizer_matches_origin",
        ),
        CheckConstraint(
            "(format = 'OFFLINE' AND location_id IS NOT NULL AND online_url IS NULL) OR "
            "(format = 'ONLINE' AND location_id IS NULL AND online_url IS NOT NULL) OR "
            "(format = 'HYBRID' AND location_id IS NOT NULL AND online_url IS NOT NULL)",
            name="location_matches_format",
        ),
        CheckConstraint(
            "(price_type = 'FREE' AND price_min IS NULL AND price_max IS NULL "
            "AND currency IS NULL) OR "
            "(price_type = 'PAID' AND price_min IS NOT NULL AND price_min >= 0 "
            "AND (price_max IS NULL OR price_max >= price_min) AND currency IS NOT NULL)",
            name="price_fields_match_type",
        ),
        Index("ix_events_discovery", "status", "visibility", "published_at"),
        Index("ix_events_organizer_user_status", "organizer_user_id", "status"),
        Index(
            "ix_events_organizer_organization_status", "organizer_organization_id", "status"
        ),
        Index("ix_events_location_status", "location_id", "status"),
        Index("ix_events_price", "price_type", "price_min", "price_max"),
        Index("ix_events_search_document", "search_document", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    search_document: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('russian', coalesce(summary, '')), 'B') || "
            "setweight(to_tsvector('russian', coalesce(description, '')), 'C')",
            persisted=True,
        ),
    )
    origin: Mapped[EventOrigin] = mapped_column(
        Enum(EventOrigin, name="event_origin"), nullable=False
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"),
        nullable=False,
        server_default=EventStatus.DRAFT.value,
    )
    visibility: Mapped[EventVisibility] = mapped_column(
        Enum(EventVisibility, name="event_visibility"),
        nullable=False,
        server_default=EventVisibility.PUBLIC.value,
    )
    join_policy: Mapped[EventJoinPolicy] = mapped_column(
        Enum(EventJoinPolicy, name="event_join_policy"),
        nullable=False,
        server_default=EventJoinPolicy.OPEN.value,
    )
    format: Mapped[EventFormat] = mapped_column(
        Enum(EventFormat, name="event_format"), nullable=False
    )
    price_type: Mapped[EventPriceType] = mapped_column(
        Enum(EventPriceType, name="event_price_type"),
        nullable=False,
        server_default=EventPriceType.FREE.value,
    )
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    capacity: Mapped[int | None] = mapped_column(Integer)
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )
    online_url: Mapped[str | None] = mapped_column(Text)
    registration_url: Mapped[str | None] = mapped_column(Text)
    organizer_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="RESTRICT")
    )
    organizer_organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="RESTRICT")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventManager(Base):
    __tablename__ = "event_managers"
    __table_args__ = (Index("ix_event_managers_user_role", "user_id", "role"),)

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[EventManagerRole] = mapped_column(
        Enum(EventManagerRole, name="event_manager_role"),
        nullable=False,
        server_default=EventManagerRole.MANAGER.value,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventTopic(Base):
    __tablename__ = "event_topics"
    __table_args__ = (Index("ix_event_topics_topic_event", "topic_id", "event_id"),)

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecurrenceRule(Base, TimestampMixin):
    __tablename__ = "recurrence_rules"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="positive_duration",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    dtstart: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    rrule: Mapped[str] = mapped_column(Text, nullable=False)
    generate_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class EventOccurrence(Base, TimestampMixin):
    __tablename__ = "event_occurrences"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_time_range"),
        CheckConstraint(
            "capacity_override IS NULL OR capacity_override > 0",
            name="positive_capacity_override",
        ),
        UniqueConstraint("event_id", "starts_at", name="event_start"),
        Index("ix_event_occurrences_status_starts_at", "status", "starts_at"),
        Index(
            "ix_event_occurrences_recurrence_starts_at", "recurrence_rule_id", "starts_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    recurrence_rule_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recurrence_rules.id", ondelete="SET NULL")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_all_day: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[OccurrenceStatus] = mapped_column(
        Enum(OccurrenceStatus, name="occurrence_status"),
        nullable=False,
        server_default=OccurrenceStatus.SCHEDULED.value,
    )
    capacity_override: Mapped[int | None] = mapped_column(Integer)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
