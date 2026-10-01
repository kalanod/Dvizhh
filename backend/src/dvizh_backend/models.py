import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Visibility(StrEnum):
    PUBLIC = "public"
    FRIENDS = "friends"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class JoinMode(StrEnum):
    OPEN = "open"
    REQUEST = "request"
    INVITE_ONLY = "invite_only"
    EXTERNAL = "external"


class ParticipationStatus(StrEnum):
    PENDING = "pending"
    GOING = "going"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def _enum(enum_class: type[StrEnum]) -> SqlEnum:
    return SqlEnum(
        enum_class,
        native_enum=False,
        length=20,
        values_callable=lambda members: [member.value for member in members],
    )


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Дата начала обязательна, остальное — по желанию организатора.
    start_date: Mapped[date] = mapped_column(index=True)
    start_time: Mapped[time | None]
    end_date: Mapped[date | None]
    end_time: Mapped[time | None]

    is_online: Mapped[bool] = mapped_column(default=False)
    place: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)

    # None — бесплатно.
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # None — без лимита.
    max_participants: Mapped[int | None]

    visibility: Mapped[Visibility] = mapped_column(_enum(Visibility))
    join_mode: Mapped[JoinMode] = mapped_column(_enum(JoinMode))

    organizer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    organizer: Mapped[User] = relationship(lazy="joined")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Participation(Base):
    __tablename__ = "participations"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user: Mapped[User] = relationship(lazy="joined")

    status: Mapped[ParticipationStatus] = mapped_column(_enum(ParticipationStatus))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Friendship(Base):
    """Дружба взаимная: на каждую пару хранятся две строки, по одной в каждую сторону."""

    __tablename__ = "friendships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    friend_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
