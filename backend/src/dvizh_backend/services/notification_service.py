from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.models import (
    Event,
    EventFavorite,
    EventInvitation,
    EventNotification,
    EventOccurrence,
    EventParticipation,
    Profile,
)
from dvizh_backend.database.models.enums import InvitationStatus, ParticipationStatus, ProfileStatus
from dvizh_backend.database.services.exceptions import EntityNotFoundError, PermissionDeniedError

from .user_service import UserService


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def event_changed(
        self, event: Event, actor_id: UUID, *, kind: str, changed_fields: list[str]
    ) -> None:
        follows = exists().where(
            EventFavorite.user_id == Profile.id, EventFavorite.event_id == event.id
        )
        attends = exists().where(
            EventParticipation.user_id == Profile.id,
            EventParticipation.occurrence_id == EventOccurrence.id,
            EventOccurrence.event_id == event.id,
            EventParticipation.status.in_(
                [ParticipationStatus.GOING, ParticipationStatus.REQUESTED]
            ),
        )
        invited = exists().where(
            EventInvitation.invitee_user_id == Profile.id,
            EventInvitation.occurrence_id == EventOccurrence.id,
            EventOccurrence.event_id == event.id,
            EventInvitation.status == InvitationStatus.PENDING,
            or_(EventInvitation.expires_at.is_(None), EventInvitation.expires_at > func.now()),
        )
        recipients = (
            await self.session.scalars(
                select(Profile.id).where(
                    Profile.id != actor_id,
                    Profile.status == ProfileStatus.ACTIVE,
                    Profile.deleted_at.is_(None),
                    or_(follows, attends, invited),
                )
            )
        ).all()
        self.session.add_all(
            EventNotification(
                user_id=user_id,
                event_id=event.id,
                actor_id=actor_id,
                kind=kind,
                payload={"title": event.title, "changed_fields": sorted(changed_fields)},
            )
            for user_id in recipients
        )
        await self.session.flush()

    async def list_for_user(
        self, user_id: UUID, *, unread_only: bool = False, offset: int = 0, limit: int = 20
    ) -> list[EventNotification]:
        await UserService(self.session).get_profile(user_id)
        statement = select(EventNotification).where(EventNotification.user_id == user_id)
        if unread_only:
            statement = statement.where(EventNotification.read_at.is_(None))
        result = await self.session.scalars(
            statement.order_by(EventNotification.created_at.desc(), EventNotification.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> EventNotification:
        await UserService(self.session).get_profile(user_id)
        notification = await self.session.scalar(
            select(EventNotification)
            .where(EventNotification.id == notification_id)
            .with_for_update()
        )
        if notification is None:
            raise EntityNotFoundError("Notification not found")
        if notification.user_id != user_id:
            raise PermissionDeniedError("Notification belongs to another user")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await self.session.flush()
        return notification
