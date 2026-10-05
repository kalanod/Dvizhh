import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from ..dto.user import FriendshipDTO, ProfileDTO
from ..services.dependencies import UserServiceDep

router = APIRouter(prefix="/api/users/{user_id}/friends", tags=["friends"])


class FriendshipResponse(BaseModel):
    accept: bool = Field(description="true — принять заявку, false — отклонить.")


@router.get("", summary="Список друзей пользователя.")
async def list_friends(user_id: uuid.UUID, users: UserServiceDep) -> list[ProfileDTO]:
    return await users.list_friends(user_id)


@router.put(
    "/{friend_id}",
    summary="Отправить заявку в друзья.",
    description=(
        "Создаёт заявку в статусе PENDING; дружба возникает, когда второй пользователь "
        "её примет. Если заявка или дружба уже есть, вернётся 409."
    ),
)
async def add_friend(
    user_id: uuid.UUID, friend_id: uuid.UUID, users: UserServiceDep
) -> FriendshipDTO:
    return await users.request_friendship(user_id, friend_id)


@router.patch(
    "/{friend_id}",
    summary="Принять или отклонить заявку в друзья.",
    description="Отвечает пользователь user_id на заявку, которую отправил friend_id.",
)
async def respond_to_friend(
    user_id: uuid.UUID, friend_id: uuid.UUID, body: FriendshipResponse, users: UserServiceDep
) -> FriendshipDTO:
    return await users.respond_to_friendship(user_id, friend_id, accept=body.accept)


@router.delete(
    "/{friend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя из друзей.",
    description="Дружба прекращается у обоих пользователей.",
)
async def remove_friend(user_id: uuid.UUID, friend_id: uuid.UUID, users: UserServiceDep) -> None:
    await users.remove_friend(user_id, friend_id)
