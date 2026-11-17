import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from dvizh_backend.api.dependencies import UserServiceDep
from dvizh_backend.api.schemas.user import FriendshipDTO, FriendshipResponse, ProfileDTO

router = APIRouter(prefix="/api/users/{user_id}/friends", tags=["friends"])


@router.get("/search", summary="Поиск друзей по имени или никнейму с пагинацией.")
async def search_friends(
    user_id: uuid.UUID, users: UserServiceDep,
    q: Annotated[str, Query(max_length=120)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ProfileDTO]:
    return await users.search_friends(user_id, q, offset=offset, limit=limit)


@router.get("", summary="Список друзей пользователя.")
async def list_friends(user_id: uuid.UUID, users: UserServiceDep) -> list[ProfileDTO]:
    return await users.list_friends(user_id)


@router.get("/{friend_id:uuid}", summary="Текущее состояние дружбы двух пользователей.")
async def get_friendship(
    user_id: uuid.UUID, friend_id: uuid.UUID, users: UserServiceDep,
) -> FriendshipDTO | None:
    return await users.get_friendship(user_id, friend_id)


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
    summary="Удалить пользователя из друзей или отменить исходящую заявку.",
    description="Дружба прекращается у обоих. Отменить заявку может только её отправитель.",
)
async def remove_friend(user_id: uuid.UUID, friend_id: uuid.UUID, users: UserServiceDep) -> None:
    await users.remove_friend(user_id, friend_id)
