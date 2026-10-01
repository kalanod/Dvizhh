import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_, delete, func, or_, select

from ..db import SessionDep
from ..models import Friendship, User
from ..schemas import UserResponse

router = APIRouter(prefix="/api/users/{user_id}/friends", tags=["friends"])


@router.get("", summary="Список друзей пользователя.")
async def list_friends(user_id: uuid.UUID, session: SessionDep) -> list[UserResponse]:
    if await session.get(User, user_id) is None:
        raise HTTPException(404, "Пользователь не найден.")

    friends = await session.scalars(
        select(User)
        .join(Friendship, Friendship.friend_id == User.id)
        .where(Friendship.user_id == user_id)
        .order_by(User.display_name)
    )
    return [UserResponse.model_validate(friend) for friend in friends]


@router.put(
    "/{friend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Добавить пользователя в друзья.",
    description=(
        "Дружба взаимная и возникает сразу, без подтверждения: оба пользователя появляются "
        "в списках друзей друг друга. Повторный вызов ничего не меняет."
    ),
)
async def add_friend(user_id: uuid.UUID, friend_id: uuid.UUID, session: SessionDep) -> None:
    if user_id == friend_id:
        raise HTTPException(400, "Нельзя добавить в друзья самого себя.")

    found = await session.scalar(
        select(func.count()).select_from(User).where(User.id.in_([user_id, friend_id]))
    )
    if found != 2:
        raise HTTPException(404, "Пользователь не найден.")

    if await session.get(Friendship, (user_id, friend_id)) is None:
        session.add(Friendship(user_id=user_id, friend_id=friend_id))
        session.add(Friendship(user_id=friend_id, friend_id=user_id))
        await session.commit()


@router.delete(
    "/{friend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя из друзей.",
    description="Дружба удаляется у обоих пользователей.",
)
async def remove_friend(user_id: uuid.UUID, friend_id: uuid.UUID, session: SessionDep) -> None:
    result = await session.execute(
        delete(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            )
        )
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Пользователи не являются друзьями.")
