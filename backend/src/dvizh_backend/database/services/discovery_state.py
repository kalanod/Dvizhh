from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.models import DiscoveryPage, DiscoverySession


class DiscoveryState:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, session_id: UUID, now: datetime, expires_at: datetime) -> None:
        expired = (
            select(DiscoverySession.id)
            .where(DiscoverySession.expires_at <= now)
            .order_by(DiscoverySession.expires_at)
            .limit(32)
            .with_for_update(skip_locked=True)
        )
        await self.db.execute(delete(DiscoverySession).where(DiscoverySession.id.in_(expired)))
        self.db.add(DiscoverySession(id=session_id, expires_at=expires_at))
        await self.db.flush()

    async def active(
        self, session_id: UUID, now: datetime, *, lock: bool = False
    ) -> DiscoverySession | None:
        statement = select(DiscoverySession).where(
            DiscoverySession.id == session_id, DiscoverySession.expires_at > now
        )
        if lock:
            statement = statement.with_for_update()
        return await self.db.scalar(statement)

    async def page(self, session_id: UUID, page: int) -> DiscoveryPage | None:
        return await self.db.get(DiscoveryPage, (session_id, page))

    async def renew(self, session_id: UUID, now: datetime, expires_at: datetime) -> bool:
        updated = await self.db.scalar(
            update(DiscoverySession)
            .where(DiscoverySession.id == session_id, DiscoverySession.expires_at > now)
            .values(expires_at=func.greatest(DiscoverySession.expires_at, expires_at))
            .returning(DiscoverySession.id)
        )
        return updated is not None

    async def delivered_recommendations(self, session_id: UUID, before: int) -> list[UUID]:
        pages = await self.db.scalars(
            select(DiscoveryPage.items).where(
                DiscoveryPage.session_id == session_id,
                DiscoveryPage.page < before,
                DiscoveryPage.request_id.is_not(None),
            )
        )
        return [UUID(item_id) for pairs in pages for item_id, _ in pairs]

    def save(self, page: DiscoveryPage) -> None:
        self.db.add(page)
