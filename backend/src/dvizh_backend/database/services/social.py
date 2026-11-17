from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Friendship, Profile
from ..models.enums import FriendshipStatus, ProfileStatus


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
            select(Friendship)
            .where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
            )
            .order_by(
                Friendship.responded_at.desc(), Friendship.user_low_id, Friendship.user_high_id
            )
        )
        return list(result.all())

    async def search_friends(
        self, user_id: UUID, query: str, *, offset: int, limit: int,
    ) -> list[Profile]:
        other_id = case(
            (Friendship.user_low_id == user_id, Friendship.user_high_id),
            else_=Friendship.user_low_id,
        )
        statement = select(Profile).join(Friendship, Profile.id == other_id).where(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
            Profile.status == ProfileStatus.ACTIVE,
        )
        if query:
            statement = statement.where(or_(
                func.lower(Profile.display_name).contains(query.lower(), autoescape=True),
                func.lower(Profile.username).contains(query.lower(), autoescape=True),
            ))
        result = await self.session.scalars(statement.order_by(
            func.lower(Profile.display_name), Profile.id,
        ).offset(offset).limit(limit))
        return list(result.all())

    async def list_pending(
        self, user_id: UUID, *, incoming: bool, offset: int = 0, limit: int = 20
    ) -> list[Friendship]:
        direction = (
            Friendship.requested_by_user_id != user_id
            if incoming
            else Friendship.requested_by_user_id == user_id
        )
        result = await self.session.scalars(
            select(Friendship)
            .where(
                Friendship.status == FriendshipStatus.PENDING,
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
                direction,
            )
            .order_by(
                Friendship.requested_at.desc(), Friendship.user_low_id, Friendship.user_high_id
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())
