from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Tag, TagCategory
from ..database.services.exceptions import EntityNotFoundError
from ..database.services.tags import TagRepository
from ..dto.tag import (
    CategoryCreateDTO,
    CategoryDTO,
    CategoryTagsDTO,
    CategoryUpdateDTO,
    TagCreateDTO,
    TagDTO,
    TagUpdateDTO,
)


class CatalogConflictError(Exception):
    pass


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TagRepository(session)

    async def catalog(self, *, include_inactive: bool = False) -> list[CategoryTagsDTO]:
        categories = await self.repository.categories()
        tags = await self.repository.tags(include_inactive=include_inactive)
        return [
            CategoryTagsDTO(
                **CategoryDTO.model_validate(category).model_dump(),
                tags=[TagDTO.model_validate(tag) for tag in tags if tag.category_id == category.id],
            )
            for category in categories
        ]

    async def create_category(self, data: CategoryCreateDTO) -> CategoryDTO:
        category = TagCategory(**data.model_dump())
        await self._save(category)
        return CategoryDTO.model_validate(category)

    async def update_category(self, category_id: UUID, data: CategoryUpdateDTO) -> CategoryDTO:
        category = await self._category(category_id)
        await self._save(category, data.model_dump(exclude_unset=True))
        return CategoryDTO.model_validate(category)

    async def delete_category(self, category_id: UUID) -> None:
        category = await self._category(category_id)
        if await self.repository.category_is_used(category_id):
            raise CatalogConflictError("Move or delete the category's tags first")
        await self.session.delete(category)
        await self.session.flush()

    async def create_tag(self, data: TagCreateDTO) -> TagDTO:
        await self._category(data.category_id)
        tag = Tag(**data.model_dump())
        await self._save(tag)
        return TagDTO.model_validate(tag)

    async def update_tag(self, tag_id: UUID, data: TagUpdateDTO) -> TagDTO:
        tag = await self._tag(tag_id)
        if data.category_id is not None:
            await self._category(data.category_id)
        await self._save(tag, data.model_dump(exclude_unset=True))
        return TagDTO.model_validate(tag)

    async def delete_tag(self, tag_id: UUID) -> None:
        tag = await self._tag(tag_id)
        if await self.repository.tag_is_used(tag_id):
            raise CatalogConflictError("Tag is used by events; deactivate it instead")
        await self.session.delete(tag)
        await self.session.flush()

    async def _tag(self, tag_id: UUID) -> Tag:
        tag = await self.repository.get_tag(tag_id)
        if tag is None:
            raise EntityNotFoundError("Tag not found")
        return tag

    async def _category(self, category_id: UUID) -> TagCategory:
        category = await self.repository.get_category(category_id)
        if category is None:
            raise EntityNotFoundError("Tag category not found")
        return category

    async def _save(self, entity: Tag | TagCategory, fields: dict | None = None) -> None:
        try:
            async with self.session.begin_nested():
                for name, value in (fields or {}).items():
                    setattr(entity, name, value)
                self.session.add(entity)
                await self.session.flush()
        except IntegrityError:
            raise CatalogConflictError("Catalog entry conflicts with an existing entry") from None
