from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

USER_ROLE_ID = UUID("741abca2-761f-5f9c-b35d-8b1efa9ef675")
ADMIN_ROLE_ID = UUID("76524bee-a7f4-51b5-8b58-bb300ee09f3e")


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("name IN ('user', 'admin')", name="ck_roles_name"),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("username ~ '^[a-z0-9_]{3,50}$'", name="ck_accounts_username"),
        CheckConstraint("email IS NULL OR email = lower(btrim(email))", name="ck_accounts_email"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    role_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        default=USER_ROLE_ID,
        server_default=text(f"'{USER_ROLE_ID}'"),
    )
    role: Mapped[Role] = relationship(lazy="joined")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
