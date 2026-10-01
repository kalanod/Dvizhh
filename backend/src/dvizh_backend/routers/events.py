import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionDep
from ..models import (
    Event,
    Friendship,
    JoinMode,
    Participation,
    ParticipationStatus,
    User,
    Visibility,
)
from ..queries import fetch_events, going_count, select_events
from ..schemas import (
    EventCreate,
    EventResponse,
    EventUpdate,
    JoinRequest,
    ParticipantResponse,
    ReviewRequest,
)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get(
    "",
    summary="Лента публичных событий.",
    description=(
        "Возвращает только события с видимостью public, сортировка «По новизне» "
        "(по времени публикации). Все фильтры необязательны и комбинируются между собой. "
        "Если указан friends_of, среди подходящих под фильтры событий первыми идут те, "
        "на которые идёт больше друзей пользователя; события без друзей остаются в выдаче "
        "и идут после них."
    ),
)
async def list_events(
    session: SessionDep,
    q: Annotated[str | None, Query(description="Поиск по подстроке в названии и описании.")] = None,
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
) -> list[EventResponse]:
    query = select_events().where(Event.visibility == Visibility.PUBLIC)

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Event.title.ilike(pattern), Event.description.ilike(pattern)))
    if tag and tag.strip():
        query = query.where(Event.tags.contains([tag.strip().lower()]))
    if date_from is not None:
        query = query.where(func.coalesce(Event.end_date, Event.start_date) >= date_from)
    if date_to is not None:
        query = query.where(Event.start_date <= date_to)
    if free_only:
        query = query.where(Event.price.is_(None))
    if available_only:
        query = query.where(
            or_(Event.max_participants.is_(None), going_count < Event.max_participants)
        )

    if friends_of is not None:
        friend_ids = select(Friendship.friend_id).where(Friendship.user_id == friends_of)
        friends_going = (
            select(func.count())
            .select_from(Participation)
            .where(
                Participation.event_id == Event.id,
                Participation.status == ParticipationStatus.GOING,
                Participation.user_id.in_(friend_ids),
            )
            .correlate(Event)
            .scalar_subquery()
        )
        query = query.order_by(friends_going.desc())

    query = query.order_by(Event.created_at.desc()).offset(offset).limit(limit)
    return await fetch_events(session, query)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать событие.",
    description=(
        "Обязательны название, дата начала и организатор. Цена не указана или 0 — событие "
        "бесплатное; max_participants не указан — без лимита участников."
    ),
)
async def create_event(body: EventCreate, session: SessionDep) -> EventResponse:
    if await session.get(User, body.organizer_id) is None:
        raise HTTPException(404, "Организатор не найден.")

    event = Event(**body.to_columns())
    session.add(event)
    await session.commit()
    return await _load_event(session, event.id)


@router.get(
    "/{event_id}",
    summary="Получить событие по идентификатору.",
    description="Работает для событий с любой видимостью.",
)
async def get_event(event_id: uuid.UUID, session: SessionDep) -> EventResponse:
    return await _load_event(session, event_id)


@router.put(
    "/{event_id}",
    summary="Изменить параметры события.",
    description="Заменяет все поля события переданными значениями. Организатор не меняется.",
)
async def update_event(
    event_id: uuid.UUID, body: EventUpdate, session: SessionDep
) -> EventResponse:
    event = await _get_event(session, event_id)
    for column, value in body.to_columns().items():
        setattr(event, column, value)
    await session.commit()
    return await _load_event(session, event_id)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить событие.",
    description="Вместе с событием удаляются все заявки и участия.",
)
async def delete_event(event_id: uuid.UUID, session: SessionDep) -> None:
    result = await session.execute(delete(Event).where(Event.id == event_id))
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Событие не найдено.")


@router.get(
    "/{event_id}/participants",
    summary="Список участников события.",
    description="Возвращает участников (going) и ожидающие решения заявки (pending).",
)
async def list_participants(event_id: uuid.UUID, session: SessionDep) -> list[ParticipantResponse]:
    await _get_event(session, event_id)
    participations = await session.scalars(
        select(Participation)
        .where(
            Participation.event_id == event_id,
            Participation.status.in_([ParticipationStatus.GOING, ParticipationStatus.PENDING]),
        )
        .order_by(Participation.updated_at)
    )
    return [ParticipantResponse.model_validate(p) for p in participations]


@router.post(
    "/{event_id}/participants",
    summary="«Иду»: присоединиться к событию.",
    description=(
        "Для событий open пользователь сразу становится участником, если есть свободные места. "
        "Для request создаётся заявка, которую рассматривает организатор. К событиям "
        "invite_only и external присоединиться нельзя. Повторная заявка после отклонения "
        "недоступна."
    ),
)
async def join_event(
    event_id: uuid.UUID, body: JoinRequest, session: SessionDep
) -> ParticipantResponse:
    event = await _get_event(session, event_id)
    user = await session.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден.")

    if event.join_mode in (JoinMode.INVITE_ONLY, JoinMode.EXTERNAL):
        raise HTTPException(409, "К этому событию нельзя присоединиться напрямую.")

    participation = await session.get(Participation, (event_id, user.id))
    if participation is not None:
        if participation.status in (ParticipationStatus.GOING, ParticipationStatus.PENDING):
            raise HTTPException(409, "Пользователь уже участвует или отправил заявку.")
        if participation.status == ParticipationStatus.REJECTED:
            raise HTTPException(409, "Заявка отклонена, повторная подача недоступна.")

    is_open = event.join_mode == JoinMode.OPEN
    if is_open and await _is_full(session, event):
        raise HTTPException(409, "Мест нет.")

    if participation is None:
        participation = Participation(event_id=event_id, user=user)
        session.add(participation)

    participation.status = ParticipationStatus.GOING if is_open else ParticipationStatus.PENDING
    participation.updated_at = datetime.now(UTC)
    await session.commit()
    return ParticipantResponse.model_validate(participation)


@router.patch(
    "/{event_id}/participants/{user_id}",
    summary="Принять или отклонить заявку на участие.",
    description=(
        "Действие организатора. Рассмотреть можно только заявку в статусе pending; "
        "принять нельзя, если мест уже нет."
    ),
)
async def review_participation(
    event_id: uuid.UUID, user_id: uuid.UUID, body: ReviewRequest, session: SessionDep
) -> ParticipantResponse:
    participation = await session.get(Participation, (event_id, user_id))
    if participation is None:
        raise HTTPException(404, "Заявка не найдена.")
    if participation.status != ParticipationStatus.PENDING:
        raise HTTPException(409, "Заявка уже рассмотрена.")

    if body.accept and await _is_full(session, await _get_event(session, event_id)):
        raise HTTPException(409, "Мест нет.")

    participation.status = (
        ParticipationStatus.GOING if body.accept else ParticipationStatus.REJECTED
    )
    participation.updated_at = datetime.now(UTC)
    await session.commit()
    return ParticipantResponse.model_validate(participation)


@router.delete(
    "/{event_id}/participants/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить участие или отозвать заявку.",
)
async def leave_event(event_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> None:
    participation = await session.get(Participation, (event_id, user_id))
    if participation is None or participation.status in (
        ParticipationStatus.REJECTED,
        ParticipationStatus.CANCELLED,
    ):
        raise HTTPException(404, "Участие не найдено.")

    participation.status = ParticipationStatus.CANCELLED
    participation.updated_at = datetime.now(UTC)
    await session.commit()


async def _get_event(session: AsyncSession, event_id: uuid.UUID) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Событие не найдено.")
    return event


async def _load_event(session: AsyncSession, event_id: uuid.UUID) -> EventResponse:
    events = await fetch_events(session, select_events().where(Event.id == event_id))
    if not events:
        raise HTTPException(404, "Событие не найдено.")
    return events[0]


async def _is_full(session: AsyncSession, event: Event) -> bool:
    if event.max_participants is None:
        return False
    going = await session.scalar(
        select(func.count())
        .select_from(Participation)
        .where(
            Participation.event_id == event.id,
            Participation.status == ParticipationStatus.GOING,
        )
    )
    return going >= event.max_participants
