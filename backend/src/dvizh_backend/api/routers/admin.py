from uuid import UUID

from fastapi import APIRouter, Depends

from dvizh_backend.api.dependencies import TagServiceDep
from dvizh_backend.api.schemas.tag import (
    CategoryCreateDTO,
    CategoryDTO,
    CategoryTagsDTO,
    CategoryUpdateDTO,
    TagCreateDTO,
    TagDTO,
    TagUpdateDTO,
)
from dvizh_backend.api.security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/tags", summary="Каталог тематик, включая отключённые.")
async def catalog(service: TagServiceDep) -> list[CategoryTagsDTO]:
    return await service.catalog(include_inactive=True)


@router.post("/tag-categories", status_code=201, summary="Создать категорию тематик.")
async def create_category(data: CategoryCreateDTO, service: TagServiceDep) -> CategoryDTO:
    return await service.create_category(data)


@router.patch("/tag-categories/{category_id}", summary="Изменить категорию тематик.")
async def update_category(
    category_id: UUID,
    data: CategoryUpdateDTO,
    service: TagServiceDep,
) -> CategoryDTO:
    return await service.update_category(category_id, data)


@router.delete("/tag-categories/{category_id}", status_code=204,
               summary="Удалить пустую категорию тематик.")
async def delete_category(category_id: UUID, service: TagServiceDep) -> None:
    await service.delete_category(category_id)


@router.post("/tags", status_code=201, summary="Создать тематику.")
async def create_tag(data: TagCreateDTO, service: TagServiceDep) -> TagDTO:
    return await service.create_tag(data)


@router.patch("/tags/{tag_id}", summary="Изменить тематику.")
async def update_tag(tag_id: UUID, data: TagUpdateDTO, service: TagServiceDep) -> TagDTO:
    return await service.update_tag(tag_id, data)


@router.delete("/tags/{tag_id}", status_code=204, summary="Удалить тематику.")
async def delete_tag(tag_id: UUID, service: TagServiceDep) -> None:
    await service.delete_tag(tag_id)
