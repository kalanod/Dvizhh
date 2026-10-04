from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .common import TimestampMixin


class ExternalSource(Base, TimestampMixin):
    __tablename__ = "external_sources"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ExternalEventLink(Base):
    __tablename__ = "external_event_links"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="source_external_id"),
        UniqueConstraint("event_id", "source_id", name="event_source"),
        Index("ix_external_event_links_last_synced", "last_synced_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("external_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
