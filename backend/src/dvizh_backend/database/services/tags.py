from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EventTag, Tag, TagCategory


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[TagCategory]:
        result = await self.session.scalars(
            select(TagCategory).order_by(TagCategory.sort_order, TagCategory.name, TagCategory.id)
        )
        return list(result)

    async def tags(self, *, include_inactive: bool = False) -> list[Tag]:
        statement = select(Tag).order_by(Tag.sort_order, Tag.name, Tag.id)
        if not include_inactive:
            statement = statement.where(Tag.is_active.is_(True))
        return list(await self.session.scalars(statement))

    async def get_tag(self, tag_id: UUID) -> Tag | None:
        return await self.session.scalar(select(Tag).where(Tag.id == tag_id).with_for_update())

    async def get_category(self, category_id: UUID) -> TagCategory | None:
        return await self.session.scalar(
            select(TagCategory).where(TagCategory.id == category_id).with_for_update()
        )

    async def tag_is_used(self, tag_id: UUID) -> bool:
        return bool(await self.session.scalar(select(exists().where(EventTag.tag_id == tag_id))))

    async def category_is_used(self, category_id: UUID) -> bool:
        return bool(
            await self.session.scalar(select(exists().where(Tag.category_id == category_id)))
        )

    async def selected(self, tag_ids: Iterable[UUID]) -> list[Tag]:
        return list(
            await self.session.scalars(
                select(Tag)
                .where(Tag.id.in_(list(tag_ids)))
                .order_by(Tag.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
