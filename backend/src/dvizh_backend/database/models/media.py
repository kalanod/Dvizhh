from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .common import TimestampMixin
from .enums import EventMediaRole, MediaStatus, StoryStatus


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="non_negative_size"),
        CheckConstraint("width IS NULL OR width > 0", name="positive_width"),
        CheckConstraint("height IS NULL OR height > 0", name="positive_height"),
        UniqueConstraint("bucket", "object_key", name="storage_object"),
        Index("ix_media_assets_uploader_created", "uploaded_by_user_id", "created_at"),
        Index("ix_media_assets_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False
    )
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="media_status"),
        nullable=False,
        server_default=MediaStatus.UPLOADING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventMedia(Base):
    __tablename__ = "event_media"
    __table_args__ = (
        Index("ix_event_media_event_role_sort", "event_id", "role", "sort_order"),
        Index(
            "uq_event_media_cover",
            "event_id",
            unique=True,
            postgresql_where=text("role = 'COVER'"),
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[EventMediaRole] = mapped_column(
        Enum(EventMediaRole, name="event_media_role"),
        nullable=False,
        server_default=EventMediaRole.GALLERY.value,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventStory(Base, TimestampMixin):
    __tablename__ = "event_stories"
    __table_args__ = (
        Index("ix_event_stories_event_status_published", "event_id", "status", "published_at"),
        Index("ix_event_stories_occurrence_status", "occurrence_id", "status"),
        Index("ix_event_stories_creator_created", "created_by_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("event_occurrences.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[StoryStatus] = mapped_column(
        Enum(StoryStatus, name="story_status"),
        nullable=False,
        server_default=StoryStatus.DRAFT.value,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoryItem(Base):
    __tablename__ = "story_items"
    __table_args__ = (Index("ix_story_items_story_sort", "story_id", "sort_order"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    story_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("event_stories.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    caption: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
