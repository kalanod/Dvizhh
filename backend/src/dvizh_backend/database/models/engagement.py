from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .common import TimestampMixin
from .enums import InvitationStatus, ParticipationStatus


class EventFavorite(Base):
    __tablename__ = "event_favorites"
    __table_args__ = (Index("ix_event_favorites_event_created_at", "event_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventDismissal(Base):
    __tablename__ = "event_dismissals"
    __table_args__ = (
        Index("ix_event_dismissals_event_created_at", "event_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventParticipation(Base, TimestampMixin):
    __tablename__ = "event_participations"
    __table_args__ = (
        UniqueConstraint("occurrence_id", "user_id", name="occurrence_user"),
        Index("ix_event_participations_occurrence_status", "occurrence_id", "status"),
        Index("ix_event_participations_user_status_created", "user_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    occurrence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_occurrences.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ParticipationStatus] = mapped_column(
        Enum(ParticipationStatus, name="participation_status"), nullable=False
    )
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))


class ParticipationStatusHistory(Base):
    __tablename__ = "participation_status_history"
    __table_args__ = (
        Index("ix_participation_history_participation_changed", "participation_id", "changed_at"),
        Index("ix_participation_history_actor_changed", "changed_by_user_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    participation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_participations.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[ParticipationStatus | None] = mapped_column(
        Enum(ParticipationStatus, name="participation_status", create_type=False)
    )
    to_status: Mapped[ParticipationStatus] = mapped_column(
        Enum(ParticipationStatus, name="participation_status", create_type=False), nullable=False
    )
    changed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventInvitation(Base, TimestampMixin):
    __tablename__ = "event_invitations"
    __table_args__ = (
        CheckConstraint("inviter_user_id <> invitee_user_id", name="different_users"),
        UniqueConstraint("occurrence_id", "invitee_user_id", name="occurrence_invitee"),
        Index("ix_event_invitations_invitee_status", "invitee_user_id", "status", "created_at"),
        Index("ix_event_invitations_inviter_created", "inviter_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    occurrence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_occurrences.id", ondelete="CASCADE"),
        nullable=False,
    )
    inviter_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    invitee_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"),
        nullable=False,
        server_default=InvitationStatus.PENDING.value,
    )
    message: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
