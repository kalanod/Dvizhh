from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from ..dto.event import CreateEventDTO, EventDTO
from ..services.dependencies import EventServiceDep, NotificationServiceDep

router = APIRouter(prefix="/api", tags=["lifecycle"])


class ActorDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: UUID


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_id: UUID
    actor_id: UUID | None
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


@router.post("/events/drafts", status_code=201, summary="Создать заполненный черновик.")
async def create_draft(body: CreateEventDTO, events: EventServiceDep) -> EventDTO:
    return await events.create_event(body, draft=True)


@router.get("/users/{user_id}/drafts", summary="Черновики пользователя.")
async def list_drafts(
    user_id: UUID,
    events: EventServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EventDTO]:
    return await events.list_drafts(user_id, offset=offset, limit=limit)


@router.post("/events/{event_id}/publish", summary="Опубликовать черновик.")
async def publish_event(event_id: UUID, body: ActorDTO, events: EventServiceDep) -> EventDTO:
    return await events.publish(event_id, body.actor_id)


@router.post("/events/{event_id}/cancel", summary="Отменить событие.")
async def cancel_event(event_id: UUID, body: ActorDTO, events: EventServiceDep) -> EventDTO:
    return await events.cancel_event(event_id, body.actor_id)


@router.get("/users/{user_id}/notifications", summary="Уведомления об изменениях событий.")
async def list_notifications(
    user_id: UUID,
    notifications: NotificationServiceDep,
    unread_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[NotificationDTO]:
    return [
        NotificationDTO.model_validate(item)
        for item in await notifications.list_for_user(
            user_id, unread_only=unread_only, offset=offset, limit=limit
        )
    ]


@router.put(
    "/users/{user_id}/notifications/{notification_id}/read", summary="Отметить прочитанным."
)
async def mark_read(
    user_id: UUID, notification_id: UUID, notifications: NotificationServiceDep
) -> NotificationDTO:
    return NotificationDTO.model_validate(await notifications.mark_read(notification_id, user_id))
