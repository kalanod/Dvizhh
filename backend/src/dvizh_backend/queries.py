from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Event, Participation, ParticipationStatus
from .schemas import EventResponse

# Количество участников события со статусом «иду».
going_count = (
    select(func.count())
    .select_from(Participation)
    .where(
        Participation.event_id == Event.id,
        Participation.status == ParticipationStatus.GOING,
    )
    .correlate(Event)
    .scalar_subquery()
)


def select_events() -> Select:
    return select(Event, going_count.label("participants_count"))


async def fetch_events(session: AsyncSession, query: Select) -> list[EventResponse]:
    rows = await session.execute(query)
    return [
        EventResponse.model_validate({**event.__dict__, "participants_count": count})
        for event, count in rows
    ]
