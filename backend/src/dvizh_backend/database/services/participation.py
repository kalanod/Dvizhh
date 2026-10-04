from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Event,
    EventInvitation,
    EventOccurrence,
    EventParticipation,
    ParticipationStatusHistory,
)
from ..models.enums import (
    EventJoinPolicy,
    EventStatus,
    InvitationStatus,
    OccurrenceStatus,
    ParticipationStatus,
)
from .access import can_manage_event
from .exceptions import (
    CapacityReachedError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    JoinUnavailableError,
    PermissionDeniedError,
)


class ParticipationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def join(self, occurrence_id: UUID, user_id: UUID) -> EventParticipation:
        occurrence, event = await self._lock_occurrence_and_event(occurrence_id)
        self._require_joinable(occurrence, event)

        participation = await self._get_participation(occurrence.id, user_id, lock=True)
        if participation is not None and participation.status in {
            ParticipationStatus.GOING,
            ParticipationStatus.REQUESTED,
        }:
            return participation
        if participation is not None and participation.status == ParticipationStatus.REJECTED:
            raise InvalidStateTransitionError("A rejected request cannot be submitted again")

        if event.join_policy == EventJoinPolicy.EXTERNAL:
            raise JoinUnavailableError("Participation is handled by an external system")
        if event.join_policy == EventJoinPolicy.INVITE_ONLY:
            raise JoinUnavailableError("This event requires an invitation")

        target_status = (
            ParticipationStatus.GOING
            if event.join_policy == EventJoinPolicy.OPEN
            else ParticipationStatus.REQUESTED
        )
        if target_status == ParticipationStatus.GOING:
            await self._require_capacity(occurrence, event)

        return await self._set_status(
            participation,
            occurrence_id=occurrence.id,
            user_id=user_id,
            target_status=target_status,
            actor_user_id=user_id,
        )

    async def decide_request(
        self,
        participation_id: UUID,
        actor_user_id: UUID,
        *,
        approve: bool,
        reason: str | None = None,
    ) -> EventParticipation:
        participation = await self.session.scalar(
            select(EventParticipation)
            .where(EventParticipation.id == participation_id)
            .with_for_update()
        )
        if participation is None:
            raise EntityNotFoundError("Participation not found")
        if participation.status != ParticipationStatus.REQUESTED:
            raise InvalidStateTransitionError("Only a pending request can be decided")

        occurrence, event = await self._lock_occurrence_and_event(participation.occurrence_id)
        if not await can_manage_event(self.session, event, actor_user_id):
            raise PermissionDeniedError("User cannot decide requests for this event")

        target_status = ParticipationStatus.GOING if approve else ParticipationStatus.REJECTED
        if approve:
            self._require_joinable(occurrence, event)
            await self._require_capacity(occurrence, event)

        return await self._set_status(
            participation,
            occurrence_id=occurrence.id,
            user_id=participation.user_id,
            target_status=target_status,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    async def cancel(self, occurrence_id: UUID, user_id: UUID) -> EventParticipation:
        await self._lock_occurrence_and_event(occurrence_id)
        participation = await self._get_participation(occurrence_id, user_id, lock=True)
        if participation is None or participation.status not in {
            ParticipationStatus.GOING,
            ParticipationStatus.REQUESTED,
        }:
            raise InvalidStateTransitionError("There is no active participation to cancel")

        return await self._set_status(
            participation,
            occurrence_id=occurrence_id,
            user_id=user_id,
            target_status=ParticipationStatus.CANCELLED,
            actor_user_id=user_id,
        )

    async def accept_invitation(
        self, invitation_id: UUID, user_id: UUID
    ) -> EventParticipation:
        invitation = await self.session.scalar(
            select(EventInvitation)
            .where(EventInvitation.id == invitation_id)
            .with_for_update()
        )
        if invitation is None:
            raise EntityNotFoundError("Invitation not found")
        if invitation.invitee_user_id != user_id:
            raise PermissionDeniedError("Invitation belongs to another user")
        if invitation.status != InvitationStatus.PENDING:
            raise InvalidStateTransitionError("Invitation is no longer pending")

        now = datetime.now(UTC)
        if invitation.expires_at is not None and invitation.expires_at <= now:
            raise InvalidStateTransitionError("Invitation has expired")

        occurrence, event = await self._lock_occurrence_and_event(invitation.occurrence_id)
        self._require_joinable(occurrence, event)
        await self._require_capacity(occurrence, event)

        participation = await self._get_participation(occurrence.id, user_id, lock=True)
        if participation is not None and participation.status == ParticipationStatus.REJECTED:
            raise InvalidStateTransitionError("Rejected participation cannot be restored")

        participation = await self._set_status(
            participation,
            occurrence_id=occurrence.id,
            user_id=user_id,
            target_status=ParticipationStatus.GOING,
            actor_user_id=user_id,
        )
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = now
        await self.session.flush()
        return participation

    async def _lock_occurrence_and_event(
        self, occurrence_id: UUID
    ) -> tuple[EventOccurrence, Event]:
        row = (
            await self.session.execute(
                select(EventOccurrence, Event)
                .join(Event, Event.id == EventOccurrence.event_id)
                .where(EventOccurrence.id == occurrence_id)
                .with_for_update(of=EventOccurrence)
            )
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError("Event occurrence not found")
        return row.EventOccurrence, row.Event

    @staticmethod
    def _require_joinable(occurrence: EventOccurrence, event: Event) -> None:
        if event.status != EventStatus.PUBLISHED:
            raise JoinUnavailableError("Event is not published")
        if occurrence.status != OccurrenceStatus.SCHEDULED:
            raise JoinUnavailableError("Event occurrence is not scheduled")

    async def _require_capacity(self, occurrence: EventOccurrence, event: Event) -> None:
        capacity = occurrence.capacity_override
        if capacity is None:
            capacity = event.capacity
        if capacity is None:
            return

        going_count = await self.session.scalar(
            select(func.count(EventParticipation.id)).where(
                EventParticipation.occurrence_id == occurrence.id,
                EventParticipation.status == ParticipationStatus.GOING,
            )
        )
        if (going_count or 0) >= capacity:
            raise CapacityReachedError("No places are available")

    async def _get_participation(
        self, occurrence_id: UUID, user_id: UUID, *, lock: bool
    ) -> EventParticipation | None:
        statement = select(EventParticipation).where(
            EventParticipation.occurrence_id == occurrence_id,
            EventParticipation.user_id == user_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def _set_status(
        self,
        participation: EventParticipation | None,
        *,
        occurrence_id: UUID,
        user_id: UUID,
        target_status: ParticipationStatus,
        actor_user_id: UUID,
        reason: str | None = None,
    ) -> EventParticipation:
        now = datetime.now(UTC)
        previous_status = participation.status if participation is not None else None
        if participation is None:
            participation = EventParticipation(
                occurrence_id=occurrence_id,
                user_id=user_id,
                status=target_status,
            )
            self.session.add(participation)
            await self.session.flush()
        else:
            participation.status = target_status

        if target_status == ParticipationStatus.REQUESTED:
            participation.requested_at = now
            participation.decided_at = None
            participation.decided_by_user_id = None
            participation.cancelled_at = None
        elif target_status == ParticipationStatus.GOING:
            participation.joined_at = now
            participation.cancelled_at = None
            if previous_status == ParticipationStatus.REQUESTED:
                participation.decided_at = now
                participation.decided_by_user_id = actor_user_id
        elif target_status == ParticipationStatus.REJECTED:
            participation.decided_at = now
            participation.decided_by_user_id = actor_user_id
            participation.rejection_reason = reason
        elif target_status == ParticipationStatus.CANCELLED:
            participation.cancelled_at = now

        self.session.add(
            ParticipationStatusHistory(
                participation_id=participation.id,
                from_status=previous_status,
                to_status=target_status,
                changed_by_user_id=actor_user_id,
                reason=reason,
            )
        )
        await self.session.flush()
        return participation
