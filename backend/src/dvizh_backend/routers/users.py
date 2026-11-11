import uuid

import jwt
from fastapi import APIRouter, Cookie, HTTPException, status
from pydantic import ConfigDict, Field

from ..dto.event import EventDTO
from ..dto.user import CreateProfileDTO, ProfileDTO
from ..services.dependencies import EventServiceDep, UserServiceDep
from ..config import get_settings

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(CreateProfileDTO):
    # Тело запроса приходит из JSON, где UUID и координаты — строки и числа.
    model_config = ConfigDict(strict=False)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description=(
            "Идентификатор, выданный auth-сервисом. Пока авторизации нет, "
            "можно не передавать — он будет сгенерирован."
        ),
    )

@router.get("/me", summary="Получить профиль текущего пользователя.")
async def get_me(
    users: UserServiceDep,
    dvizh_access: str | None = Cookie(default=None),
) -> ProfileDTO:
    if not dvizh_access:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication unavailable",
        )

    try:
        claims = jwt.decode(
            dvizh_access,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    return await users.get_profile(user_id)

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
