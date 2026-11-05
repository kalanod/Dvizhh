from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Event,
    EventInvitation,
    EventManager,
    EventOccurrence,
    EventParticipation,
    Friendship,
    OrganizationMember,
)
from ..models.enums import (
    EventStatus,
    EventVisibility,
    FriendshipStatus,
    InvitationStatus,
    OrganizationRole,
    ParticipationStatus,
)


async def can_view_event_media(session: AsyncSession, event: Event, user_id: UUID | None) -> bool:
    if event.deleted_at is not None:
        return False
    if user_id is not None and await can_manage_event(session, event, user_id):
        return True
    if event.status == EventStatus.DRAFT:
        return False
    if event.visibility in {EventVisibility.PUBLIC, EventVisibility.UNLISTED}:
        return True
    if user_id is None:
        return False
    if event.visibility == EventVisibility.FRIENDS and event.organizer_user_id is not None:
        low, high = sorted([event.organizer_user_id, user_id], key=lambda value: value.int)
        return bool(
            await session.scalar(
                select(
                    exists().where(
                        Friendship.user_low_id == low,
                        Friendship.user_high_id == high,
                        Friendship.status == FriendshipStatus.ACCEPTED,
                    )
                )
            )
        )
    if event.visibility == EventVisibility.PRIVATE:
        invited = exists().where(
            EventInvitation.invitee_user_id == user_id,
            EventInvitation.occurrence_id == EventOccurrence.id,
            EventOccurrence.event_id == event.id,
            or_(
                EventInvitation.status == InvitationStatus.ACCEPTED,
                (EventInvitation.status == InvitationStatus.PENDING)
                & or_(
                    EventInvitation.expires_at.is_(None), EventInvitation.expires_at > func.now()
                ),
            ),
        )
        attending = exists().where(
            EventParticipation.user_id == user_id,
            EventParticipation.occurrence_id == EventOccurrence.id,
            EventOccurrence.event_id == event.id,
            EventParticipation.status == ParticipationStatus.GOING,
        )
        return bool(await session.scalar(select(or_(invited, attending))))
    return False


async def can_manage_event(session: AsyncSession, event: Event, user_id: UUID) -> bool:
    if event.organizer_user_id == user_id:
        return True

    manager_exists = await session.scalar(
        select(exists().where(EventManager.event_id == event.id, EventManager.user_id == user_id))
    )
    if manager_exists:
        return True

    if event.organizer_organization_id is None:
        return False

    return bool(
        await session.scalar(
            select(
                exists().where(
                    OrganizationMember.organization_id == event.organizer_organization_id,
                    OrganizationMember.user_id == user_id,
                    or_(
                        OrganizationMember.role == OrganizationRole.OWNER,
                        OrganizationMember.role == OrganizationRole.ADMIN,
                        OrganizationMember.role == OrganizationRole.EDITOR,
                    ),
                )
            )
        )
    )
