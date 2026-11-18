from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from dvizh_backend.api.dependencies import AccountContextDep, AdminUserServiceDep, TagServiceDep
from dvizh_backend.api.schemas.admin_user import (
    AdminUserDTO,
    AdminUserPage,
    ChangeRoleCommand,
    ResetPasswordCommand,
)
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


@router.get("/users", summary="Поиск учётных записей.")
async def list_users(
    service: AdminUserServiceDep,
    context: AccountContextDep,
    response: Response,
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> AdminUserPage:
    response.headers["Cache-Control"] = "no-store"
    return await service.search(q, offset, limit, context)


@router.patch("/users/{user_id}/role", summary="Изменить роль учётной записи.")
async def change_user_role(
    user_id: UUID,
    data: ChangeRoleCommand,
    service: AdminUserServiceDep,
    context: AccountContextDep,
    response: Response,
) -> AdminUserDTO:
    response.headers["Cache-Control"] = "no-store"
    return await service.change_role(user_id, data, context)


@router.post("/users/{user_id}/password", status_code=204, summary="Задать новый пароль.")
async def reset_user_password(
    user_id: UUID,
    data: ResetPasswordCommand,
    service: AdminUserServiceDep,
    context: AccountContextDep,
) -> Response:
    await service.reset_password(user_id, data, context)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


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
