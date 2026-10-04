from uuid import UUID

from sqlalchemy import select

from ..models import ExternalSource, Location, MediaAsset, Organization, Profile, Topic
from ..models.enums import ProfileStatus
from .base import BaseCRUDService


class ProfileService(BaseCRUDService[Profile]):
    model = Profile

    async def get_by_username(self, username: str) -> Profile | None:
        return await self.session.scalar(select(Profile).where(Profile.username == username))

    async def get_for_update(self, user_id: UUID) -> Profile | None:
        statement = select(Profile).where(Profile.id == user_id).with_for_update()
        return await self.session.scalar(statement)

    async def list_active(self, *, offset: int = 0, limit: int = 50) -> list[Profile]:
        result = await self.session.scalars(
            select(Profile)
            .where(Profile.status == ProfileStatus.ACTIVE)
            .order_by(Profile.created_at.desc(), Profile.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def list_active_by_ids(self, user_ids: list[UUID]) -> list[Profile]:
        if not user_ids:
            return []
        result = await self.session.scalars(
            select(Profile).where(Profile.id.in_(user_ids), Profile.status == ProfileStatus.ACTIVE)
        )
        return list(result.all())


class OrganizationService(BaseCRUDService[Organization]):
    model = Organization


class TopicService(BaseCRUDService[Topic]):
    model = Topic


class LocationService(BaseCRUDService[Location]):
    model = Location


class MediaAssetService(BaseCRUDService[MediaAsset]):
    model = MediaAsset


class ExternalSourceService(BaseCRUDService[ExternalSource]):
    model = ExternalSource
