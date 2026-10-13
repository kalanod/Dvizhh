import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from dvizh_backend.database.models import Event, EventOccurrence, Profile
from dvizh_backend.database.models.enums import (
    EventFormat,
    EventJoinPolicy,
    EventPriceType,
    EventStatus,
    EventVisibility,
    ParticipationStatus,
    ProfileStatus,
)
from dvizh_backend.database.services.event_queries import EventQueryService, EventRow
from dvizh_backend.database.services.exceptions import EntityNotFoundError
from dvizh_backend.dto.event import CreateEventDTO, UpdateEventDTO
from dvizh_backend.main import app
from dvizh_backend.routers.errors import STATUS_BY_ERROR
from dvizh_backend.services.errors import UserNotFoundError
from dvizh_backend.services.event_service import EventService

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("00000000-0000-0000-0000-00000000000a")
OCCURRENCE_ID = UUID("00000000-0000-0000-0000-00000000000b")
STARTS_AT = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)
LOCATION = {"name": "Антикафе", "latitude": "59.9343", "longitude": "30.3351"}


def test_openapi_lists_endpoints() -> None:
    paths = app.openapi()["paths"]

    assert "/api/events" in paths
    assert "/api/events/{event_id}/participants" in paths
    assert "/api/users/{user_id}/friends/{friend_id}" in paths
    assert "/api/users/{user_id}/calendar" in paths


def test_every_domain_error_has_http_status() -> None:
    assert STATUS_BY_ERROR[EntityNotFoundError] == 404
    assert set(STATUS_BY_ERROR) <= set(app.exception_handlers)


def test_event_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateEventDTO(
            title="Поход",
            starts_at=STARTS_AT,
            ends_at=STARTS_AT - timedelta(hours=1),
            location=LOCATION,
        )


def test_event_format_requires_matching_place_and_link() -> None:
    with pytest.raises(ValidationError):
        UpdateEventDTO(title="Поход", starts_at=STARTS_AT)
    with pytest.raises(ValidationError):
        UpdateEventDTO(title="Стрим", starts_at=STARTS_AT, format="ONLINE", location=LOCATION)

    online = UpdateEventDTO(
        title="Стрим", starts_at=STARTS_AT, format="ONLINE", online_url="https://example.com"
    )
    assert online.event_columns()["format"] == EventFormat.ONLINE


def test_event_columns_are_normalized() -> None:
    event = UpdateEventDTO(
        title="  Настолки ",
        starts_at=STARTS_AT,
        tags=["Игры", "игры ", ""],
        price_min=0,
        location=LOCATION,
    )

    columns = event.event_columns()

    assert columns["title"] == "Настолки"
    assert event.tags == ["игры"]
    assert columns["price_type"] == EventPriceType.FREE
    assert columns["price_min"] is None
    assert columns["currency"] is None

    paid = UpdateEventDTO(
        title="Концерт", starts_at=STARTS_AT, price_min="500.00", location=LOCATION
    ).event_columns()
    assert paid["price_type"] == EventPriceType.PAID
    assert paid["price_min"] == Decimal("500.00")
    assert paid["currency"] == "RUB"


def test_feed_query_compiles_for_postgres_with_all_filters() -> None:
    async def scenario() -> str:
        session = AsyncMock()
        session.execute.return_value = []
        await EventQueryService(session).list_public(
            text_query="настолки",
            tag="игры",
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            free_only=True,
            available_only=True,
            friends_of=USER_ID,
        )
        statement = session.execute.await_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect()))

    sql = asyncio.run(scenario())

    assert "websearch_to_tsquery" in sql
    assert "friendships" in sql
    assert "events.deleted_at IS NULL" in sql
    # Сначала события, на которые идут друзья, затем по новизне.
    assert sql.index("DESC") < sql.index("events.published_at DESC")


def make_event_service() -> EventService:
    service = EventService(AsyncMock())
    now = datetime.now(UTC)
    profile = Profile(
        id=USER_ID, username="first", display_name="First", status=ProfileStatus.ACTIVE
    )
    event = Event(
        id=EVENT_ID,
        slug="nastolki",
        title="Настолки",
        description="",
        format=EventFormat.ONLINE,
        online_url="https://example.com",
        price_type=EventPriceType.FREE,
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        join_policy=EventJoinPolicy.OPEN,
        organizer_user_id=USER_ID,
        published_at=now,
        created_at=now,
    )
    occurrence = EventOccurrence(
        id=OCCURRENCE_ID,
        event_id=EVENT_ID,
        starts_at=STARTS_AT,
        timezone="Europe/Moscow",
        is_all_day=False,
    )
    service.profiles.get_by_id = AsyncMock(return_value=profile)
    service.queries.get_primary = AsyncMock(return_value=EventRow(event, occurrence, 3))
    service.queries.topic_slugs = AsyncMock(return_value={EVENT_ID: ["игры"]})
    service.queries.locations = AsyncMock(return_value={})
    service.queries.profiles = AsyncMock(return_value={USER_ID: profile})
    return service


def test_event_is_assembled_from_event_occurrence_and_lookups() -> None:
    async def scenario() -> None:
        event = await make_event_service().get_event(EVENT_ID)

        assert event.occurrence_id == OCCURRENCE_ID
        assert event.starts_at == STARTS_AT
        assert event.tags == ["игры"]
        assert event.participants_count == 3
        assert event.organizer is not None
        assert event.organizer.username == "first"
        assert event.location is None

    asyncio.run(scenario())


def test_create_event_publishes_it_with_one_occurrence() -> None:
    async def scenario() -> None:
        service = make_event_service()
        service.queries.ensure_topics = AsyncMock(return_value=[])
        service.events.create_with_occurrence = AsyncMock()
        data = CreateEventDTO(
            title="Настолки",
            starts_at=STARTS_AT,
            format="ONLINE",
            online_url="https://example.com",
            organizer_id=USER_ID,
        )

        await service.create_event(data)

        event, occurrence = service.events.create_with_occurrence.await_args.args
        assert event.status == EventStatus.PUBLISHED
        assert event.published_at is not None
        assert event.organizer_user_id == USER_ID
        assert event.slug.startswith("настолки-")
        assert occurrence.starts_at == STARTS_AT

    asyncio.run(scenario())


def test_join_goes_through_the_event_occurrence() -> None:
    async def scenario() -> None:
        service = make_event_service()
        service.participations.join = AsyncMock(
            return_value=MagicMock(status=ParticipationStatus.GOING)
        )

        participant = await service.join(EVENT_ID, USER_ID)

        service.participations.join.assert_awaited_once_with(OCCURRENCE_ID, USER_ID)
        assert participant.status == ParticipationStatus.GOING
        assert participant.user.id == USER_ID

        service.profiles.get_by_id.return_value = None
        with pytest.raises(UserNotFoundError):
            await service.join(EVENT_ID, USER_ID)

    asyncio.run(scenario())


def test_missing_event_is_reported_before_any_write() -> None:
    async def scenario() -> None:
        service = make_event_service()
        service.queries.get_primary.return_value = None
        service.participations.join = AsyncMock()

        with pytest.raises(EntityNotFoundError):
            await service.join(EVENT_ID, USER_ID)
        service.participations.join.assert_not_awaited()

    asyncio.run(scenario())
