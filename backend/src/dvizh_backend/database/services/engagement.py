from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Event,
    EventDismissal,
    EventFavorite,
    EventInteraction,
    EventInvitation,
    EventOccurrence,
)
from ..models.enums import (
    EventJoinPolicy,
    EventStatus,
    InteractionType,
    InvitationStatus,
    OccurrenceStatus,
)
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
        inserted = await self.session.scalar(
            insert(EventFavorite)
            .values(user_id=user_id, event_id=event_id)
            .on_conflict_do_nothing()
            .returning(EventFavorite.event_id)
        )
        if inserted is not None:
            await self.record_interaction(
                user_id=user_id, event_id=event_id, interaction_type=InteractionType.FAVORITE_ADD
            )
        return await self.session.get(EventFavorite, (user_id, event_id))

    async def remove_favorite(self, user_id: UUID, event_id: UUID) -> None:
        removed = await self.session.scalar(
            delete(EventFavorite)
            .where(
                EventFavorite.user_id == user_id,
                EventFavorite.event_id == event_id,
            )
            .returning(EventFavorite.event_id)
        )
        if removed is not None:
            await self.record_interaction(
                user_id=user_id,
                event_id=event_id,
                interaction_type=InteractionType.FAVORITE_REMOVE,
            )

    async def dismiss(self, user_id: UUID, event_id: UUID) -> EventDismissal:
        inserted = await self.session.scalar(
            insert(EventDismissal)
            .values(user_id=user_id, event_id=event_id)
            .on_conflict_do_nothing()
            .returning(EventDismissal.event_id)
        )
        if inserted is not None:
            await self.record_interaction(
                user_id=user_id, event_id=event_id, interaction_type=InteractionType.NOT_INTERESTED
            )
        return await self.session.get(EventDismissal, (user_id, event_id))

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

    async def get(self, invitation_id: UUID) -> EventInvitation:
        invitation = await self.session.get(EventInvitation, invitation_id)
        if invitation is None:
            raise EntityNotFoundError("Invitation not found")
        return invitation

    async def invite(
        self,
        *,
        occurrence_id: UUID,
        inviter_user_id: UUID,
        invitee_user_id: UUID,
        message: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventInvitation:
        if inviter_user_id == invitee_user_id:
            raise InvalidStateTransitionError("Cannot invite yourself")
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise InvalidStateTransitionError("Invitation expiry must be in the future")
        row = (
            await self.session.execute(
                select(EventOccurrence).where(EventOccurrence.id == occurrence_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise EntityNotFoundError("Event occurrence not found")
        if row.status != OccurrenceStatus.SCHEDULED:
            raise InvalidStateTransitionError("Cannot invite to this occurrence")

        event = await self.session.get(Event, row.event_id)
        if event is None:
            raise EntityNotFoundError("Event not found")
        if event.deleted_at is not None or event.status != EventStatus.PUBLISHED:
            raise InvalidStateTransitionError("Event is not published")
        if event.join_policy == EventJoinPolicy.EXTERNAL:
            raise InvalidStateTransitionError("Participation is handled by an external system")
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
            if invitation.status == InvitationStatus.ACCEPTED:
                raise InvalidStateTransitionError("Invitation has already been accepted")
            if invitation.status == InvitationStatus.PENDING and (
                invitation.expires_at is None or invitation.expires_at > datetime.now(UTC)
            ):
                return invitation
            invitation.inviter_user_id = inviter_user_id
            invitation.status = InvitationStatus.PENDING
            invitation.message = message
            invitation.expires_at = expires_at
            invitation.responded_at = None

        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def decline(self, invitation_id: UUID, user_id: UUID) -> EventInvitation:
        invitation = await self.session.scalar(
            select(EventInvitation).where(EventInvitation.id == invitation_id).with_for_update()
        )
        if invitation is None:
            raise EntityNotFoundError("Invitation not found")
        if invitation.invitee_user_id != user_id:
            raise PermissionDeniedError("Invitation belongs to another user")
        if invitation.status == InvitationStatus.DECLINED:
            return invitation
        if invitation.status != InvitationStatus.PENDING or (
            invitation.expires_at is not None and invitation.expires_at <= datetime.now(UTC)
        ):
            raise InvalidStateTransitionError("Invitation is no longer pending")

        invitation.status = InvitationStatus.DECLINED
        invitation.responded_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def list_incoming(
        self, user_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[EventInvitation]:
        result = await self.session.scalars(
            select(EventInvitation)
            .join(EventOccurrence, EventOccurrence.id == EventInvitation.occurrence_id)
            .join(Event, Event.id == EventOccurrence.event_id)
            .where(
                EventInvitation.invitee_user_id == user_id,
                EventInvitation.status == InvitationStatus.PENDING,
                or_(EventInvitation.expires_at.is_(None), EventInvitation.expires_at > func.now()),
                Event.deleted_at.is_(None),
                Event.status == EventStatus.PUBLISHED,
                EventOccurrence.status == OccurrenceStatus.SCHEDULED,
            )
            .order_by(EventInvitation.created_at.desc(), EventInvitation.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def revoke(self, invitation_id: UUID, actor_id: UUID) -> EventInvitation:
        invitation = await self.session.get(EventInvitation, invitation_id)
        if invitation is None:
            raise EntityNotFoundError("Invitation not found")
        occurrence = await self.session.get(EventOccurrence, invitation.occurrence_id)
        if occurrence is None:
            raise EntityNotFoundError("Event occurrence not found")
        event = await self.session.get(Event, occurrence.event_id)
        if event is None:
            raise EntityNotFoundError("Event not found")
        if not await can_manage_event(self.session, event, actor_id):
            raise PermissionDeniedError("User cannot revoke this invitation")
        invitation = await self.session.scalar(
            select(EventInvitation)
            .where(EventInvitation.id == invitation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if invitation.status == InvitationStatus.REVOKED:
            return invitation
        if invitation.status != InvitationStatus.PENDING:
            raise InvalidStateTransitionError("Only pending invitations can be revoked")
        invitation.status = InvitationStatus.REVOKED
        invitation.responded_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation
