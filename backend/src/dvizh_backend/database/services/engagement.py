from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Event,
    EventDismissal,
    EventFavorite,
    EventInteraction,
    EventInvitation,
    EventOccurrence,
)
from ..models.enums import InteractionType, InvitationStatus, OccurrenceStatus
from .access import can_manage_event
from .exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
)


class EngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_favorite(self, user_id: UUID, event_id: UUID) -> EventFavorite:
        favorite = await self.session.get(EventFavorite, (user_id, event_id))
        if favorite is None:
            favorite = EventFavorite(user_id=user_id, event_id=event_id)
            self.session.add(favorite)
            await self.session.flush()
        return favorite

    async def remove_favorite(self, user_id: UUID, event_id: UUID) -> None:
        await self.session.execute(
            delete(EventFavorite).where(
                EventFavorite.user_id == user_id,
                EventFavorite.event_id == event_id,
            )
        )

    async def dismiss(self, user_id: UUID, event_id: UUID) -> EventDismissal:
        dismissal = await self.session.get(EventDismissal, (user_id, event_id))
        if dismissal is None:
            dismissal = EventDismissal(user_id=user_id, event_id=event_id)
            self.session.add(dismissal)
            await self.session.flush()
        return dismissal

    async def undo_dismissal(self, user_id: UUID, event_id: UUID) -> None:
        await self.session.execute(
            delete(EventDismissal).where(
                EventDismissal.user_id == user_id,
                EventDismissal.event_id == event_id,
            )
        )

    async def record_interaction(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        interaction_type: InteractionType,
        occurrence_id: UUID | None = None,
        request_id: UUID | None = None,
        session_id: UUID | None = None,
        feed_kind: str | None = None,
        position: int | None = None,
        dwell_ms: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> EventInteraction:
        interaction = EventInteraction(
            user_id=user_id,
            event_id=event_id,
            occurrence_id=occurrence_id,
            type=interaction_type,
            request_id=request_id,
            session_id=session_id,
            feed_kind=feed_kind,
            position=position,
            dwell_ms=dwell_ms,
            context=context,
        )
        self.session.add(interaction)
        await self.session.flush()
        return interaction


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def invite(
        self,
        *,
        occurrence_id: UUID,
        inviter_user_id: UUID,
        invitee_user_id: UUID,
        message: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventInvitation:
        row = (
            await self.session.execute(
                select(EventOccurrence)
                .where(EventOccurrence.id == occurrence_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise EntityNotFoundError("Event occurrence not found")
        if row.status != OccurrenceStatus.SCHEDULED:
            raise InvalidStateTransitionError("Cannot invite to this occurrence")

        event = await self.session.get(Event, row.event_id)
        if event is None:
            raise EntityNotFoundError("Event not found")
        if not await can_manage_event(self.session, event, inviter_user_id):
            raise PermissionDeniedError("User cannot invite participants to this event")

        invitation = await self.session.scalar(
            select(EventInvitation)
            .where(
                EventInvitation.occurrence_id == occurrence_id,
                EventInvitation.invitee_user_id == invitee_user_id,
            )
            .with_for_update()
        )
        if invitation is None:
            invitation = EventInvitation(
                occurrence_id=occurrence_id,
                inviter_user_id=inviter_user_id,
                invitee_user_id=invitee_user_id,
                message=message,
                expires_at=expires_at,
            )
            self.session.add(invitation)
        else:
            invitation.inviter_user_id = inviter_user_id
            invitation.status = InvitationStatus.PENDING
            invitation.message = message
            invitation.expires_at = expires_at
            invitation.responded_at = None

        await self.session.flush()
        return invitation

    async def decline(self, invitation_id: UUID, user_id: UUID) -> EventInvitation:
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

        invitation.status = InvitationStatus.DECLINED
        invitation.responded_at = datetime.now(UTC)
        await self.session.flush()
        return invitation
