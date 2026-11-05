from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from ..dto.event import EventDTO
from ..dto.invitation import CreateInvitationDTO, InvitationCardDTO, InvitationDTO
from ..dto.user import FriendshipRequestDTO, ProfileDTO, UpdateProfileDTO
from ..services.dependencies import EventServiceDep, UserServiceDep

router = APIRouter(prefix="/api", tags=["personal"])
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


class ProfilePatch(UpdateProfileDTO):
    # HTTP receives JSON strings; the domain DTO remains strict.
    model_config = ConfigDict(extra="forbid", from_attributes=True, strict=False)


class InvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    accept: bool


@router.patch("/users/{user_id}", summary="Изменить свой профиль.")
async def update_profile(user_id: UUID, body: ProfilePatch, users: UserServiceDep) -> ProfileDTO:
    return await users.update_profile(
        user_id, UpdateProfileDTO(**body.model_dump(exclude_unset=True))
    )


@router.get("/users/{user_id}/events", summary="Мои события: созданные, участия или заявки.")
async def list_my_events(
    user_id: UUID,
    events: EventServiceDep,
    kind: Literal["organized", "participating", "requested"] = "organized",
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[EventDTO]:
    return await events.list_personal(user_id, kind=kind, offset=offset, limit=limit)


@router.get("/users/{user_id}/favorites", summary="Избранные события.")
async def list_favorites(
    user_id: UUID,
    events: EventServiceDep,
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[EventDTO]:
    return await events.list_personal(user_id, kind="favorites", offset=offset, limit=limit)


@router.put("/users/{user_id}/favorites/{event_id}", summary="Сохранить событие в избранное.")
async def add_favorite(user_id: UUID, event_id: UUID, events: EventServiceDep) -> EventDTO:
    return await events.set_favorite(event_id, user_id, enabled=True)


@router.delete("/users/{user_id}/favorites/{event_id}", summary="Удалить событие из избранного.")
async def remove_favorite(user_id: UUID, event_id: UUID, events: EventServiceDep) -> EventDTO:
    return await events.set_favorite(event_id, user_id, enabled=False)


@router.get("/users/{user_id}/dismissed", summary="События, отмеченные «Не интересно».")
async def list_dismissed(
    user_id: UUID,
    events: EventServiceDep,
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[EventDTO]:
    return await events.list_personal(user_id, kind="dismissed", offset=offset, limit=limit)


@router.put("/users/{user_id}/dismissed/{event_id}", summary="Отметить «Не интересно».")
async def dismiss_event(user_id: UUID, event_id: UUID, events: EventServiceDep) -> EventDTO:
    return await events.set_dismissed(event_id, user_id, enabled=True)


@router.delete("/users/{user_id}/dismissed/{event_id}", summary="Отменить «Не интересно».")
async def restore_event(user_id: UUID, event_id: UUID, events: EventServiceDep) -> EventDTO:
    return await events.set_dismissed(event_id, user_id, enabled=False)


@router.get("/users/{user_id}/friends/requests", summary="Входящие или исходящие заявки в друзья.")
async def list_friend_requests(
    user_id: UUID,
    users: UserServiceDep,
    direction: Literal["incoming", "outgoing"] = "incoming",
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[FriendshipRequestDTO]:
    return await users.list_friendship_requests(
        user_id, incoming=direction == "incoming", offset=offset, limit=limit
    )


@router.post("/events/{event_id}/invitations", summary="Пригласить пользователя на событие.")
async def invite_to_event(
    event_id: UUID, body: CreateInvitationDTO, events: EventServiceDep
) -> InvitationDTO:
    return await events.invite(event_id, body)


@router.get("/users/{user_id}/invitations", summary="Действующие входящие приглашения.")
async def list_invitations(
    user_id: UUID,
    events: EventServiceDep,
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[InvitationCardDTO]:
    return await events.list_invitations(user_id, offset=offset, limit=limit)


@router.patch("/invitations/{invitation_id}", summary="Принять или отклонить приглашение.")
async def respond_to_invitation(
    invitation_id: UUID, body: InvitationResponse, events: EventServiceDep
) -> InvitationDTO:
    return await events.respond_to_invitation(invitation_id, body.user_id, accept=body.accept)


@router.delete("/invitations/{invitation_id}", summary="Отозвать приглашение организатором.")
async def revoke_invitation(
    invitation_id: UUID, actor_id: UUID, events: EventServiceDep
) -> InvitationDTO:
    return await events.revoke_invitation(invitation_id, actor_id)
