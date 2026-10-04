from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Friendship
from ..models.enums import FriendshipStatus


class FriendshipService:
    """Direct friendship persistence. State transitions belong to UserService."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_pair(
        self, user_low_id: UUID, user_high_id: UUID, *, for_update: bool = False
    ) -> Friendship | None:
        statement = select(Friendship).where(
            Friendship.user_low_id == user_low_id,
            Friendship.user_high_id == user_high_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def add(self, friendship: Friendship) -> Friendship:
        self.session.add(friendship)
        await self.session.flush()
        return friendship

    async def flush(self) -> None:
        await self.session.flush()

    async def list_accepted_for_user(self, user_id: UUID) -> list[Friendship]:
        result = await self.session.scalars(
            select(Friendship).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
            ).order_by(
                Friendship.responded_at.desc(), Friendship.user_low_id, Friendship.user_high_id
            )
        )
        return list(result.all())
