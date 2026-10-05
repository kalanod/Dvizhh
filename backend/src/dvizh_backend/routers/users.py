import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from ..dto.event import EventDTO
from ..dto.user import CreateProfileDTO, ProfileDTO
from ..services.dependencies import EventServiceDep, UserServiceDep

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    id: uuid.UUID | None = Field(
        None,
        description=(
            "Идентификатор, выданный auth-сервисом. Пока авторизации нет, "
            "можно не передавать — он будет сгенерирован."
        ),
    )
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
        description="Уникальное имя пользователя: строчные латинские буквы, цифры и «_».",
    )
    display_name: str = Field(min_length=1, max_length=120, description="Отображаемое имя.")
    bio: str | None = Field(None, max_length=2000, description="О себе.")
    city: str | None = Field(None, min_length=1, max_length=120, description="Город.")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя.",
    description="Username должен быть уникальным, иначе вернётся 409.",
)
async def create_user(body: UserCreate, users: UserServiceDep) -> ProfileDTO:
    data = body.model_dump()
    data["id"] = body.id or uuid.uuid4()
    return await users.create_profile(CreateProfileDTO(**data))


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
