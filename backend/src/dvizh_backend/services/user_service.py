from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.models import Friendship, Profile
from dvizh_backend.database.models.enums import FriendshipStatus, MediaStatus, ProfileStatus
from dvizh_backend.database.services.catalog import MediaAssetService, ProfileService
from dvizh_backend.database.services.social import FriendshipService
from dvizh_backend.dto.user import CreateProfileDTO, FriendshipDTO, ProfileDTO, UpdateProfileDTO

from .errors import (
    AvatarUnavailableError,
    FriendshipStateError,
    ProfileAlreadyExistsError,
    UserInactiveError,
    UsernameTakenError,
    UserNotFoundError,
)


class UserService:
    """Profile and friendship rules within one request-scoped database transaction.

    The caller supplies an authenticated user ID. Credential checks and token handling
    belong to auth-api; this service owns only the core domain profile.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.profiles = ProfileService(session)
        self.friendships = FriendshipService(session)
        self.media = MediaAssetService(session)

    async def create_profile(self, data: CreateProfileDTO) -> ProfileDTO:
        if await self.profiles.get_by_id(data.id) is not None:
            raise ProfileAlreadyExistsError("Profile already exists")
        await self._require_available_username(data.username)
        await self._require_usable_avatar(data.avatar_media_id, data.id)
        profile = await self.profiles.create(**data.model_dump())
        return ProfileDTO.model_validate(profile)

    async def get_profile(self, user_id: UUID) -> ProfileDTO:
        profile = await self._require_active_profile(user_id)
        return ProfileDTO.model_validate(profile)

    async def get_profile_by_username(self, username: str) -> ProfileDTO:
        profile = await self.profiles.get_by_username(username)
        if profile is None:
            raise UserNotFoundError("Profile not found")
        self._require_active(profile)
        return ProfileDTO.model_validate(profile)

    async def list_profiles(self, *, offset: int = 0, limit: int = 50) -> list[ProfileDTO]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset must be non-negative and limit must be between 1 and 100")
        profiles = await self.profiles.list_active(offset=offset, limit=limit)
        return [ProfileDTO.model_validate(profile) for profile in profiles]

    async def update_profile(self, user_id: UUID, data: UpdateProfileDTO) -> ProfileDTO:
        profile = await self.profiles.get_for_update(user_id)
        if profile is None:
            raise UserNotFoundError("Profile not found")
        self._require_active(profile)
        changes = data.model_dump(exclude_unset=True)
        if "username" in changes and changes["username"] != profile.username:
            await self._require_available_username(changes["username"])
        if "avatar_media_id" in changes:
            await self._require_usable_avatar(changes["avatar_media_id"], user_id)
        profile = await self.profiles.update(profile, **changes)
        return ProfileDTO.model_validate(profile)

    async def request_friendship(self, user_id: UUID, other_user_id: UUID) -> FriendshipDTO:
        low_id, high_id = self._canonical_pair(user_id, other_user_id)
        await self._require_active_profile(user_id)
        await self._require_active_profile(other_user_id)
        friendship = await self.friendships.get_pair(low_id, high_id, for_update=True)
        if friendship is not None and friendship.status in {
            FriendshipStatus.PENDING,
            FriendshipStatus.ACCEPTED,
        }:
            raise FriendshipStateError("Friendship request or friendship already exists")

        now = datetime.now(UTC)
        if friendship is None:
            friendship = Friendship(
                user_low_id=low_id,
                user_high_id=high_id,
                requested_by_user_id=user_id,
                status=FriendshipStatus.PENDING,
                requested_at=now,
            )
            await self.friendships.add(friendship)
        else:
            friendship.requested_by_user_id = user_id
            friendship.status = FriendshipStatus.PENDING
            friendship.requested_at = now
            friendship.responded_at = None
            friendship.removed_at = None
            await self.friendships.flush()
        return FriendshipDTO.model_validate(friendship)

    async def respond_to_friendship(
        self, user_id: UUID, requester_id: UUID, *, accept: bool
    ) -> FriendshipDTO:
        low_id, high_id = self._canonical_pair(user_id, requester_id)
        await self._require_active_profile(user_id)
        await self._require_active_profile(requester_id)
        friendship = await self.friendships.get_pair(low_id, high_id, for_update=True)
        if (
            friendship is None
            or friendship.status != FriendshipStatus.PENDING
            or friendship.requested_by_user_id != requester_id
        ):
            raise FriendshipStateError("Pending request from this user not found")
        friendship.status = FriendshipStatus.ACCEPTED if accept else FriendshipStatus.DECLINED
        friendship.responded_at = datetime.now(UTC)
        await self.friendships.flush()
        return FriendshipDTO.model_validate(friendship)

    async def remove_friend(self, user_id: UUID, friend_id: UUID) -> FriendshipDTO:
        low_id, high_id = self._canonical_pair(user_id, friend_id)
        await self._require_active_profile(user_id)
        friendship = await self.friendships.get_pair(low_id, high_id, for_update=True)
        if friendship is None or friendship.status != FriendshipStatus.ACCEPTED:
            raise FriendshipStateError("Active friendship not found")
        friendship.status = FriendshipStatus.REMOVED
        friendship.removed_at = datetime.now(UTC)
        await self.friendships.flush()
        return FriendshipDTO.model_validate(friendship)

    async def list_friends(self, user_id: UUID) -> list[ProfileDTO]:
        await self._require_active_profile(user_id)
        friendships = await self.friendships.list_accepted_for_user(user_id)
        friend_ids = [
            friendship.user_high_id if friendship.user_low_id == user_id else friendship.user_low_id
            for friendship in friendships
        ]
        profiles = await self.profiles.list_active_by_ids(friend_ids)
        by_id = {profile.id: profile for profile in profiles}
        return [
            ProfileDTO.model_validate(by_id[friend_id])
            for friend_id in friend_ids
            if friend_id in by_id
        ]

    async def are_friends(self, first_user_id: UUID, second_user_id: UUID) -> bool:
        low_id, high_id = self._canonical_pair(first_user_id, second_user_id)
        await self._require_active_profile(first_user_id)
        await self._require_active_profile(second_user_id)
        friendship = await self.friendships.get_pair(low_id, high_id)
        return friendship is not None and friendship.status == FriendshipStatus.ACCEPTED

    async def _require_active_profile(self, user_id: UUID) -> Profile:
        profile = await self.profiles.get_by_id(user_id)
        if profile is None:
            raise UserNotFoundError("Profile not found")
        self._require_active(profile)
        return profile

    @staticmethod
    def _require_active(profile: Profile) -> None:
        if profile.status != ProfileStatus.ACTIVE:
            raise UserInactiveError("Profile is not active")

    async def _require_available_username(self, username: str) -> None:
        if await self.profiles.get_by_username(username) is not None:
            raise UsernameTakenError("Username is already taken")

    async def _require_usable_avatar(self, media_id: UUID | None, user_id: UUID) -> None:
        if media_id is None:
            return
        media = await self.media.get_by_id(media_id)
        if (
            media is None
            or media.status != MediaStatus.READY
            or media.uploaded_by_user_id != user_id
        ):
            raise AvatarUnavailableError("Avatar must be a ready media asset owned by the user")

    @staticmethod
    def _canonical_pair(first_id: UUID, second_id: UUID) -> tuple[UUID, UUID]:
        if first_id == second_id:
            raise FriendshipStateError("A user cannot befriend themselves")
        return (first_id, second_id) if first_id.int < second_id.int else (second_id, first_id)
