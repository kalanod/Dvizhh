from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DiscoverySession(Base):
    __tablename__ = "discovery_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DiscoveryPage(Base):
    __tablename__ = "discovery_pages"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    page: Mapped[int] = mapped_column(primary_key=True)
    items: Mapped[list[list[str]]] = mapped_column(JSONB)
    request_id: Mapped[UUID | None]
    next_page_token: Mapped[str | None] = mapped_column(Text)
    fallback_after: Mapped[list[object] | None] = mapped_column(JSONB(none_as_null=True))
