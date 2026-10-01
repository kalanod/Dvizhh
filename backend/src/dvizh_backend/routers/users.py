import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import exists, select

from ..db import SessionDep
from ..models import Event, Participation, ParticipationStatus, User
from ..queries import fetch_events, select_events
from ..schemas import EventResponse, UserCreate, UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя.",
    description=(
        "Username приводится к нижнему регистру и должен быть уникальным, иначе вернётся 409."
    ),
)
async def create_user(body: UserCreate, session: SessionDep) -> UserResponse:
    username = body.username.strip().lower()
    if await session.scalar(select(exists().where(User.username == username))):
        raise HTTPException(409, "Пользователь с таким username уже существует.")

    user = User(username=username, display_name=body.display_name.strip())
    session.add(user)
    await session.commit()
    return UserResponse.model_validate(user)


@router.get("/{user_id}", summary="Получить профиль пользователя по идентификатору.")
async def get_user(user_id: uuid.UUID, session: SessionDep) -> UserResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден.")
    return UserResponse.model_validate(user)


@router.get(
    "/{user_id}/calendar",
    summary="Календарь пользователя.",
    description=(
        "События, на которые пользователь идёт (статус going), "
        "по возрастанию даты и времени начала."
    ),
)
async def get_calendar(user_id: uuid.UUID, session: SessionDep) -> list[EventResponse]:
    if await session.get(User, user_id) is None:
        raise HTTPException(404, "Пользователь не найден.")

    is_going = exists().where(
        Participation.event_id == Event.id,
        Participation.user_id == user_id,
        Participation.status == ParticipationStatus.GOING,
    )
    query = (
        select_events().where(is_going).order_by(Event.start_date, Event.start_time.nulls_first())
    )
    return await fetch_events(session, query)
