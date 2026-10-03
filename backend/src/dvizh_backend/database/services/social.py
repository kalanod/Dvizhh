from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Friendship
from ..models.enums import FriendshipStatus
from .exceptions import InvalidStateTransitionError, PermissionDeniedError


class FriendshipService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request(self, requester_id: UUID, addressee_id: UUID) -> Friendship:
        low_id, high_id = self._canonical_pair(requester_id, addressee_id)
        friendship = await self.session.get(
            Friendship, (low_id, high_id), with_for_update=True
        )
        if friendship is not None and friendship.status in {
            FriendshipStatus.PENDING,
            FriendshipStatus.ACCEPTED,
        }:
            return friendship

        now = datetime.now(UTC)
        if friendship is None:
            friendship = Friendship(
                user_low_id=low_id,
                user_high_id=high_id,
                requested_by_user_id=requester_id,
                status=FriendshipStatus.PENDING,
                requested_at=now,
            )
            self.session.add(friendship)
        else:
            friendship.requested_by_user_id = requester_id
            friendship.status = FriendshipStatus.PENDING
            friendship.requested_at = now
            friendship.responded_at = None
            friendship.removed_at = None

        await self.session.flush()
        return friendship

    async def respond(
        self, user_id: UUID, requester_id: UUID, *, accept: bool
    ) -> Friendship:
        friendship = await self._get_locked(user_id, requester_id)
        if friendship is None or friendship.status != FriendshipStatus.PENDING:
            raise InvalidStateTransitionError("Friend request is not pending")
        if friendship.requested_by_user_id != requester_id:
            raise PermissionDeniedError("Only the request recipient can respond")

        friendship.status = (
            FriendshipStatus.ACCEPTED if accept else FriendshipStatus.DECLINED
        )
        friendship.responded_at = datetime.now(UTC)
        await self.session.flush()
        return friendship

    async def remove(self, user_id: UUID, friend_id: UUID) -> Friendship:
        friendship = await self._get_locked(user_id, friend_id)
        if friendship is None or friendship.status != FriendshipStatus.ACCEPTED:
            raise InvalidStateTransitionError("Active friendship not found")

        friendship.status = FriendshipStatus.REMOVED
        friendship.removed_at = datetime.now(UTC)
        await self.session.flush()
        return friendship

    async def list_friend_ids(self, user_id: UUID) -> list[UUID]:
        rows = await self.session.execute(
            select(Friendship.user_low_id, Friendship.user_high_id).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
            )
        )
        return [high if low == user_id else low for low, high in rows]

    async def _get_locked(self, first_id: UUID, second_id: UUID) -> Friendship | None:
        low_id, high_id = self._canonical_pair(first_id, second_id)
        return await self.session.get(Friendship, (low_id, high_id), with_for_update=True)

    @staticmethod
    def _canonical_pair(first_id: UUID, second_id: UUID) -> tuple[UUID, UUID]:
        if first_id == second_id:
            raise InvalidStateTransitionError("A user cannot befriend themselves")
        return (first_id, second_id) if first_id.int < second_id.int else (second_id, first_id)
