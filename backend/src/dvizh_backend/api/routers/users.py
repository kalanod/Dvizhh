import uuid

from fastapi import APIRouter, status

from dvizh_backend.api.dependencies import EventServiceDep, UserServiceDep
from dvizh_backend.api.schemas.event import EventDTO
from dvizh_backend.api.schemas.user import ProfileDTO, UserCreate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя.",
    description="Username должен быть уникальным, иначе вернётся 409.",
)
async def create_user(body: UserCreate, users: UserServiceDep) -> ProfileDTO:
    return await users.create_profile(body)


@router.get("/{user_id}", summary="Получить профиль пользователя по идентификатору.")
async def get_user(user_id: uuid.UUID, users: UserServiceDep) -> ProfileDTO:
    return await users.get_profile(user_id)


@router.get(
    "/{user_id}/calendar",
    summary="Календарь пользователя.",
    description="События, на которые пользователь идёт (статус GOING), по возрастанию начала.",
)
async def get_calendar(user_id: uuid.UUID, events: EventServiceDep) -> list[EventDTO]:
    return await events.list_calendar(user_id)
