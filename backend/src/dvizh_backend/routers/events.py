import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from ..dto.event import (
    CreateEventDTO,
    EventDTO,
    JoinEventDTO,
    ParticipantDTO,
    ReviewParticipationDTO,
    UpdateEventDTO,
)
from ..services.dependencies import EventServiceDep

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get(
    "",
    summary="Лента публичных событий.",
    description=(
        "Возвращает только опубликованные события с видимостью PUBLIC, сортировка "
        "«По новизне» (по времени публикации). Все фильтры необязательны и комбинируются "
        "между собой. Если указан friends_of, среди подходящих под фильтры событий первыми "
        "идут те, на которые идёт больше друзей пользователя; события без друзей остаются "
        "в выдаче и идут после них."
    ),
)
async def list_events(
    events: EventServiceDep,
    q: Annotated[
        str | None, Query(description="Полнотекстовый поиск по названию и описанию.")
    ] = None,
    tag: Annotated[str | None, Query(description="Тематика (тег) события.")] = None,
    date_from: Annotated[
        date | None,
        Query(
            alias="from",
            description="Начало периода: события, которые заканчиваются не раньше этой даты.",
        ),
    ] = None,
    date_to: Annotated[
        date | None,
        Query(
            alias="to",
            description="Конец периода: события, которые начинаются не позже этой даты.",
        ),
    ] = None,
    free_only: Annotated[bool, Query(description="Только бесплатные события.")] = False,
    available_only: Annotated[
        bool, Query(description="Только события со свободными местами.")
    ] = False,
    friends_of: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Идентификатор пользователя: сначала показывать события, "
                "на которые идут его друзья."
            )
        ),
    ] = None,
    offset: Annotated[
        int, Query(ge=0, description="Сколько событий пропустить (для пагинации).")
    ] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Сколько событий вернуть.")] = 20,
) -> list[EventDTO]:
    return await events.list_public(
        text_query=q,
        tag=tag,
        date_from=date_from,
        date_to=date_to,
        free_only=free_only,
        available_only=available_only,
        friends_of=friends_of,
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать событие.",
    description=(
        "Событие сразу публикуется. Обязательны название, начало и организатор; для формата "
        "OFFLINE нужно место, для ONLINE — ссылка на трансляцию. Цена не указана или 0 — "
        "событие бесплатное; capacity не указан — без лимита участников."
    ),
)
async def create_event(body: CreateEventDTO, events: EventServiceDep) -> EventDTO:
    return await events.create_event(body)


@router.get(
    "/{event_id}",
    summary="Получить событие по идентификатору.",
    description="Работает для событий с любой видимостью.",
)
async def get_event(event_id: uuid.UUID, events: EventServiceDep) -> EventDTO:
    return await events.get_event(event_id)


@router.put(
    "/{event_id}",
    summary="Изменить параметры события.",
    description="Заменяет все поля события переданными значениями. Организатор не меняется.",
)
async def update_event(
    event_id: uuid.UUID, body: UpdateEventDTO, events: EventServiceDep
) -> EventDTO:
    return await events.update_event(event_id, body)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить событие.",
    description="Событие помечается удалённым и пропадает из ленты, календарей и поиска.",
)
async def delete_event(event_id: uuid.UUID, events: EventServiceDep) -> None:
    await events.delete_event(event_id)


@router.get(
    "/{event_id}/participants",
    summary="Список участников события.",
    description="Возвращает участников (GOING) и ожидающие решения заявки (REQUESTED).",
)
async def list_participants(event_id: uuid.UUID, events: EventServiceDep) -> list[ParticipantDTO]:
    return await events.list_participants(event_id)


@router.post(
    "/{event_id}/participants",
    summary="«Иду»: присоединиться к событию.",
    description=(
        "Для событий OPEN пользователь сразу становится участником, если есть свободные места. "
        "Для REQUEST создаётся заявка, которую рассматривает организатор. К событиям "
        "INVITE_ONLY и EXTERNAL присоединиться нельзя. Повторный вызов возвращает текущее "
        "участие; повторная заявка после отклонения недоступна."
    ),
)
async def join_event(
    event_id: uuid.UUID, body: JoinEventDTO, events: EventServiceDep
) -> ParticipantDTO:
    return await events.join(event_id, body.user_id)


@router.patch(
    "/{event_id}/participants/{user_id}",
    summary="Принять или отклонить заявку на участие.",
    description=(
        "Действие организатора или менеджера события. Рассмотреть можно только заявку "
        "в статусе REQUESTED; принять нельзя, если мест уже нет."
    ),
)
async def review_participation(
    event_id: uuid.UUID, user_id: uuid.UUID, body: ReviewParticipationDTO, events: EventServiceDep
) -> ParticipantDTO:
    return await events.review_participation(
        event_id, user_id, body.actor_id, accept=body.accept, reason=body.reason
    )


@router.delete(
    "/{event_id}/participants/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить участие или отозвать заявку.",
)
async def leave_event(event_id: uuid.UUID, user_id: uuid.UUID, events: EventServiceDep) -> None:
    await events.leave(event_id, user_id)
