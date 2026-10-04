from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .enums import InteractionType


class EventInteraction(Base):
    __tablename__ = "event_interactions"
    __table_args__ = (
        CheckConstraint("position IS NULL OR position >= 0", name="non_negative_position"),
        CheckConstraint("dwell_ms IS NULL OR dwell_ms >= 0", name="non_negative_dwell"),
        Index("ix_event_interactions_user_occurred", "user_id", "occurred_at"),
        Index("ix_event_interactions_event_occurred", "event_id", "occurred_at"),
        Index("ix_event_interactions_type_occurred", "type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("event_occurrences.id", ondelete="SET NULL")
    )
    type: Mapped[InteractionType] = mapped_column(
        Enum(InteractionType, name="interaction_type"), nullable=False
    )
    request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    feed_kind: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int | None] = mapped_column(Integer)
    dwell_ms: Mapped[int | None] = mapped_column(Integer)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
