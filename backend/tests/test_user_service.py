import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from dvizh_backend.database.models import Friendship, Profile
from dvizh_backend.database.models.enums import FriendshipStatus, ProfileStatus
from dvizh_backend.dto.user import CreateProfileDTO, UpdateProfileDTO
from dvizh_backend.services.errors import (
    AvatarUnavailableError,
    FriendshipStateError,
    UserInactiveError,
    UsernameTakenError,
)
from dvizh_backend.services.user_service import UserService

FIRST_ID = UUID("00000000-0000-0000-0000-000000000001")
SECOND_ID = UUID("00000000-0000-0000-0000-000000000002")


def make_profile(
    user_id: UUID, username: str, *, status: ProfileStatus = ProfileStatus.ACTIVE
) -> Profile:
    now = datetime.now(UTC)
    return Profile(
        id=user_id,
        username=username,
        display_name=username,
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_profile_dto_rejects_invalid_and_ambiguous_changes() -> None:
    with pytest.raises(ValidationError):
        CreateProfileDTO(id=FIRST_ID, username="Bad Name", display_name="Valid")
    with pytest.raises(ValidationError):
        CreateProfileDTO(id=FIRST_ID, username="valid", display_name="  ")
    with pytest.raises(ValidationError):
        UpdateProfileDTO()
    with pytest.raises(ValidationError):
        UpdateProfileDTO(latitude=Decimal("55.750000"))
    with pytest.raises(ValidationError):
        UpdateProfileDTO(display_name=None)
    with pytest.raises(ValidationError):
        UpdateProfileDTO(display_name="Valid", unknown_field=True)

    patch = UpdateProfileDTO(bio=None, latitude=None, longitude=None)
    assert patch.model_dump(exclude_unset=True) == {
        "bio": None,
        "latitude": None,
        "longitude": None,
    }


def test_profile_update_changes_only_supplied_fields() -> None:
    async def scenario() -> None:
        service = UserService(AsyncMock())
        profile = make_profile(FIRST_ID, "first")
        profile.bio = "Previous"
        service.profiles.get_for_update = AsyncMock(return_value=profile)

        async def update(entity: Profile, **changes: object) -> Profile:
            for field, value in changes.items():
                setattr(entity, field, value)
            return entity

        service.profiles.update = AsyncMock(side_effect=update)
        result = await service.update_profile(FIRST_ID, UpdateProfileDTO(bio=None))

        assert result.bio is None
        assert result.username == "first"
        service.profiles.update.assert_awaited_once_with(profile, bio=None)

    asyncio.run(scenario())


def test_profile_creation_checks_username_and_avatar_before_write() -> None:
    async def scenario() -> None:
        service = UserService(AsyncMock())
        service.profiles.get_by_id = AsyncMock(return_value=None)
        service.profiles.get_by_username = AsyncMock(return_value=make_profile(SECOND_ID, "taken"))
        service.profiles.create = AsyncMock()

        data = CreateProfileDTO(id=FIRST_ID, username="taken", display_name="First")
        with pytest.raises(UsernameTakenError):
            await service.create_profile(data)
        service.profiles.create.assert_not_awaited()

        service.profiles.get_by_username.return_value = None
        data = CreateProfileDTO(
            id=FIRST_ID,
            username="first",
            display_name="First",
            avatar_media_id=SECOND_ID,
        )
        service.media.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(AvatarUnavailableError):
            await service.create_profile(data)
        service.profiles.create.assert_not_awaited()

    asyncio.run(scenario())


def test_friendship_transition_and_actor_check() -> None:
    async def scenario() -> None:
        service = UserService(AsyncMock())
        profiles = {
            FIRST_ID: make_profile(FIRST_ID, "first"),
            SECOND_ID: make_profile(SECOND_ID, "second"),
        }
        service.profiles.get_by_id = AsyncMock(side_effect=profiles.get)
        service.friendships.get_pair = AsyncMock(return_value=None)
        service.friendships.add = AsyncMock(side_effect=lambda friendship: friendship)
        service.friendships.flush = AsyncMock()

        requested = await service.request_friendship(FIRST_ID, SECOND_ID)
        assert requested.status == FriendshipStatus.PENDING
        assert requested.requested_by_user_id == FIRST_ID

        friendship = Friendship(
            user_low_id=FIRST_ID,
            user_high_id=SECOND_ID,
            requested_by_user_id=FIRST_ID,
            status=FriendshipStatus.PENDING,
            requested_at=requested.requested_at,
        )
        service.friendships.get_pair.return_value = friendship
        with pytest.raises(FriendshipStateError):
            await service.respond_to_friendship(FIRST_ID, SECOND_ID, accept=True)

        accepted = await service.respond_to_friendship(SECOND_ID, FIRST_ID, accept=True)
        assert accepted.status == FriendshipStatus.ACCEPTED
        assert await service.are_friends(FIRST_ID, SECOND_ID)

        removed = await service.remove_friend(FIRST_ID, SECOND_ID)
        assert removed.status == FriendshipStatus.REMOVED
        assert not await service.are_friends(FIRST_ID, SECOND_ID)

    asyncio.run(scenario())


def test_inactive_profile_fails_before_friendship_write() -> None:
    async def scenario() -> None:
        service = UserService(AsyncMock())
        service.profiles.get_by_id = AsyncMock(
            side_effect=lambda user_id: make_profile(
                user_id,
                "inactive" if user_id == FIRST_ID else "second",
                status=ProfileStatus.SUSPENDED if user_id == FIRST_ID else ProfileStatus.ACTIVE,
            )
        )
        service.friendships.get_pair = AsyncMock()

        with pytest.raises(UserInactiveError):
            await service.request_friendship(FIRST_ID, SECOND_ID)
        service.friendships.get_pair.assert_not_awaited()

    asyncio.run(scenario())
