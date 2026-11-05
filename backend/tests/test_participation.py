import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from dvizh_backend.database.models import (
    Event,
    EventOccurrence,
    EventParticipation,
    ParticipationStatusHistory,
)
from dvizh_backend.database.models.enums import (
    EventJoinPolicy,
    EventStatus,
    OccurrenceStatus,
    ParticipationStatus,
)
from dvizh_backend.database.services.exceptions import (
    CapacityReachedError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    JoinUnavailableError,
    PermissionDeniedError,
)
from dvizh_backend.database.services.participation import ParticipationService

ORGANIZER_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
STRANGER_ID = UUID("00000000-0000-0000-0000-000000000003")
EVENT_ID = UUID("00000000-0000-0000-0000-00000000000a")
OCCURRENCE_ID = UUID("00000000-0000-0000-0000-00000000000b")
PARTICIPATION_ID = UUID("00000000-0000-0000-0000-00000000000c")


def make_event(
    *,
    join_policy: EventJoinPolicy = EventJoinPolicy.OPEN,
    status: EventStatus = EventStatus.PUBLISHED,
    capacity: int | None = None,
) -> Event:
    return Event(
        id=EVENT_ID,
        status=status,
        join_policy=join_policy,
        capacity=capacity,
        organizer_user_id=ORGANIZER_ID,
        organizer_organization_id=None,
    )


def make_occurrence(
    *,
    status: OccurrenceStatus = OccurrenceStatus.SCHEDULED,
    capacity_override: int | None = None,
) -> EventOccurrence:
    return EventOccurrence(
        id=OCCURRENCE_ID, event_id=EVENT_ID, status=status, capacity_override=capacity_override
    )


def make_participation(status: ParticipationStatus) -> EventParticipation:
    return EventParticipation(
        id=PARTICIPATION_ID, occurrence_id=OCCURRENCE_ID, user_id=USER_ID, status=status
    )


def make_service(
    event: Event,
    occurrence: EventOccurrence | None = None,
    *,
    participation: EventParticipation | None = None,
    participation_by_id: EventParticipation | None = None,
    scalars: list[object] | None = None,
) -> ParticipationService:
    """Service over a mocked session.

    ``participation_by_id`` is the initial lookup before locking the occurrence.
    ``scalars`` are the results of ``session.scalar`` in call order: the refreshed
    participation under lock, event manager checks and GOING participant counts.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = participation_by_id
    session.scalar.side_effect = scalars or []
    service = ParticipationService(session)
    service._lock_occurrence_and_event = AsyncMock(
        return_value=(occurrence or make_occurrence(), event)
    )
    service._get_participation = AsyncMock(return_value=participation)
    return service


def history(service: ParticipationService) -> list[ParticipationStatusHistory]:
    added = [call.args[0] for call in service.session.add.call_args_list]
    return [entity for entity in added if isinstance(entity, ParticipationStatusHistory)]


def test_join_open_event_with_free_places_makes_user_going() -> None:
    async def scenario() -> None:
        service = make_service(make_event(capacity=2), scalars=[1])

        participation = await service.join(OCCURRENCE_ID, USER_ID)

        assert participation.status == ParticipationStatus.GOING
        assert participation.user_id == USER_ID
        assert participation.joined_at is not None
        [record] = history(service)
        assert record.from_status is None
        assert record.to_status == ParticipationStatus.GOING
        assert record.changed_by_user_id == USER_ID

    asyncio.run(scenario())


def test_join_open_event_without_limit_does_not_count_participants() -> None:
    async def scenario() -> None:
        service = make_service(make_event(capacity=None))

        participation = await service.join(OCCURRENCE_ID, USER_ID)

        assert participation.status == ParticipationStatus.GOING
        service.session.scalar.assert_not_awaited()

    asyncio.run(scenario())


def test_join_full_open_event_is_rejected_without_writes() -> None:
    async def scenario() -> None:
        service = make_service(make_event(capacity=2), scalars=[2])

        with pytest.raises(CapacityReachedError):
            await service.join(OCCURRENCE_ID, USER_ID)
        service.session.add.assert_not_called()

    asyncio.run(scenario())


def test_occurrence_capacity_overrides_event_capacity() -> None:
    async def scenario() -> None:
        occurrence = make_occurrence(capacity_override=1)
        service = make_service(make_event(capacity=10), occurrence, scalars=[1])

        with pytest.raises(CapacityReachedError):
            await service.join(OCCURRENCE_ID, USER_ID)

    asyncio.run(scenario())


def test_join_request_event_creates_request_without_capacity_check() -> None:
    async def scenario() -> None:
        event = make_event(join_policy=EventJoinPolicy.REQUEST, capacity=1)
        service = make_service(event)

        participation = await service.join(OCCURRENCE_ID, USER_ID)

        assert participation.status == ParticipationStatus.REQUESTED
        assert participation.requested_at is not None
        service.session.scalar.assert_not_awaited()
        assert [record.to_status for record in history(service)] == [ParticipationStatus.REQUESTED]

    asyncio.run(scenario())


@pytest.mark.parametrize("join_policy", [EventJoinPolicy.INVITE_ONLY, EventJoinPolicy.EXTERNAL])
def test_join_is_unavailable_for_invite_only_and_external_events(
    join_policy: EventJoinPolicy,
) -> None:
    async def scenario() -> None:
        service = make_service(make_event(join_policy=join_policy))

        with pytest.raises(JoinUnavailableError):
            await service.join(OCCURRENCE_ID, USER_ID)
        service.session.add.assert_not_called()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("event_status", "occurrence_status"),
    [
        (EventStatus.DRAFT, OccurrenceStatus.SCHEDULED),
        (EventStatus.CANCELLED, OccurrenceStatus.SCHEDULED),
        (EventStatus.PUBLISHED, OccurrenceStatus.CANCELLED),
    ],
)
def test_join_requires_published_event_and_scheduled_occurrence(
    event_status: EventStatus, occurrence_status: OccurrenceStatus
) -> None:
    async def scenario() -> None:
        service = make_service(
            make_event(status=event_status), make_occurrence(status=occurrence_status)
        )

        with pytest.raises(JoinUnavailableError):
            await service.join(OCCURRENCE_ID, USER_ID)
        service._get_participation.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [ParticipationStatus.GOING, ParticipationStatus.REQUESTED])
def test_repeated_join_returns_current_participation(status: ParticipationStatus) -> None:
    async def scenario() -> None:
        existing = make_participation(status)
        # Мест нет, но повторный вызов не должен до этого дойти.
        service = make_service(make_event(capacity=1), participation=existing, scalars=[1])

        participation = await service.join(OCCURRENCE_ID, USER_ID)

        assert participation is existing
        assert participation.status == status
        assert history(service) == []

    asyncio.run(scenario())


def test_rejected_request_cannot_be_submitted_again() -> None:
    async def scenario() -> None:
        existing = make_participation(ParticipationStatus.REJECTED)
        service = make_service(
            make_event(join_policy=EventJoinPolicy.REQUEST), participation=existing
        )

        with pytest.raises(InvalidStateTransitionError):
            await service.join(OCCURRENCE_ID, USER_ID)
        assert existing.status == ParticipationStatus.REJECTED

    asyncio.run(scenario())


def test_join_after_cancellation_reuses_the_participation() -> None:
    async def scenario() -> None:
        existing = make_participation(ParticipationStatus.CANCELLED)
        service = make_service(make_event(), participation=existing)

        participation = await service.join(OCCURRENCE_ID, USER_ID)

        assert participation is existing
        assert participation.status == ParticipationStatus.GOING
        assert participation.cancelled_at is None
        [record] = history(service)
        assert record.from_status == ParticipationStatus.CANCELLED

    asyncio.run(scenario())


def test_organizer_approves_request() -> None:
    async def scenario() -> None:
        request = make_participation(ParticipationStatus.REQUESTED)
        event = make_event(join_policy=EventJoinPolicy.REQUEST, capacity=5)
        service = make_service(event, participation_by_id=request, scalars=[request, 4])

        participation = await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)

        assert participation.status == ParticipationStatus.GOING
        assert participation.decided_by_user_id == ORGANIZER_ID
        assert participation.decided_at is not None
        [record] = history(service)
        assert record.from_status == ParticipationStatus.REQUESTED
        assert record.to_status == ParticipationStatus.GOING
        assert record.changed_by_user_id == ORGANIZER_ID

    asyncio.run(scenario())


def test_request_cannot_be_approved_when_event_is_full() -> None:
    async def scenario() -> None:
        request = make_participation(ParticipationStatus.REQUESTED)
        event = make_event(join_policy=EventJoinPolicy.REQUEST, capacity=5)
        service = make_service(event, participation_by_id=request, scalars=[request, 5])

        with pytest.raises(CapacityReachedError):
            await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)
        assert request.status == ParticipationStatus.REQUESTED

    asyncio.run(scenario())


def test_organizer_rejects_request_with_reason_even_when_event_is_full() -> None:
    async def scenario() -> None:
        request = make_participation(ParticipationStatus.REQUESTED)
        event = make_event(join_policy=EventJoinPolicy.REQUEST, capacity=1)
        service = make_service(event, participation_by_id=request, scalars=[request])

        participation = await service.decide_request(
            PARTICIPATION_ID, ORGANIZER_ID, approve=False, reason="Нет мест"
        )

        assert participation.status == ParticipationStatus.REJECTED
        assert participation.rejection_reason == "Нет мест"
        assert participation.decided_by_user_id == ORGANIZER_ID
        [record] = history(service)
        assert record.to_status == ParticipationStatus.REJECTED
        assert record.reason == "Нет мест"

    asyncio.run(scenario())


@pytest.mark.parametrize("approve", [True, False])
def test_only_event_manager_can_decide_request(approve: bool) -> None:
    async def scenario() -> None:
        request = make_participation(ParticipationStatus.REQUESTED)
        event = make_event(join_policy=EventJoinPolicy.REQUEST)
        # Второй scalar — проверка, что пользователь не числится менеджером события.
        service = make_service(event, participation_by_id=request, scalars=[request, False])

        with pytest.raises(PermissionDeniedError):
            await service.decide_request(PARTICIPATION_ID, STRANGER_ID, approve=approve)
        assert request.status == ParticipationStatus.REQUESTED
        assert history(service) == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status",
    [ParticipationStatus.GOING, ParticipationStatus.REJECTED, ParticipationStatus.CANCELLED],
)
def test_only_pending_request_can_be_decided(status: ParticipationStatus) -> None:
    async def scenario() -> None:
        request = make_participation(status)
        service = make_service(make_event(), participation_by_id=request, scalars=[request])

        with pytest.raises(InvalidStateTransitionError):
            await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)
        assert request.status == status
        service.session.add.assert_not_called()
        service.session.flush.assert_not_awaited()

    asyncio.run(scenario())


def test_deciding_missing_request_is_reported() -> None:
    async def scenario() -> None:
        service = make_service(make_event())

        with pytest.raises(EntityNotFoundError):
            await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)
        service._lock_occurrence_and_event.assert_not_awaited()
        service.session.add.assert_not_called()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status",
    [ParticipationStatus.GOING, ParticipationStatus.REJECTED, ParticipationStatus.CANCELLED],
)
def test_request_changed_while_waiting_for_lock_cannot_be_decided(
    status: ParticipationStatus,
) -> None:
    async def scenario() -> None:
        initial = make_participation(ParticipationStatus.REQUESTED)
        current = make_participation(status)
        service = make_service(make_event(), participation_by_id=initial, scalars=[current])

        with pytest.raises(InvalidStateTransitionError):
            await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)
        service._lock_occurrence_and_event.assert_awaited_once_with(OCCURRENCE_ID)
        assert current.status == status
        service.session.add.assert_not_called()
        service.session.flush.assert_not_awaited()

    asyncio.run(scenario())


def test_request_deleted_while_waiting_for_lock_is_reported() -> None:
    async def scenario() -> None:
        initial = make_participation(ParticipationStatus.REQUESTED)
        service = make_service(make_event(), participation_by_id=initial, scalars=[None])

        with pytest.raises(EntityNotFoundError):
            await service.decide_request(PARTICIPATION_ID, ORGANIZER_ID, approve=True)
        service.session.add.assert_not_called()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [ParticipationStatus.GOING, ParticipationStatus.REQUESTED])
def test_cancel_active_participation(status: ParticipationStatus) -> None:
    async def scenario() -> None:
        existing = make_participation(status)
        service = make_service(make_event(), participation=existing)

        participation = await service.cancel(OCCURRENCE_ID, USER_ID)

        assert participation.status == ParticipationStatus.CANCELLED
        assert participation.cancelled_at is not None
        [record] = history(service)
        assert record.from_status == status
        assert record.to_status == ParticipationStatus.CANCELLED
        assert record.changed_by_user_id == USER_ID

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status", [None, ParticipationStatus.CANCELLED, ParticipationStatus.REJECTED]
)
def test_cancel_requires_active_participation(status: ParticipationStatus | None) -> None:
    async def scenario() -> None:
        existing = make_participation(status) if status is not None else None
        service = make_service(make_event(), participation=existing)

        with pytest.raises(InvalidStateTransitionError):
            await service.cancel(OCCURRENCE_ID, USER_ID)
        assert history(service) == []

    asyncio.run(scenario())
