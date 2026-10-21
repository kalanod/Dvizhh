import re
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.database.models import Event, EventOccurrence, Profile
from dvizh_backend.database.models.enums import EventOrigin, EventStatus, ProfileStatus
from dvizh_backend.database.services.access import can_manage_event
from dvizh_backend.database.services.catalog import LocationService, ProfileService
from dvizh_backend.database.services.engagement import EngagementService, InvitationService
from dvizh_backend.database.services.event_queries import EventQueryService, EventRow
from dvizh_backend.database.services.events import EventService as EventCRUDService
from dvizh_backend.database.services.exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
)
from dvizh_backend.database.services.participation import ParticipationService
from dvizh_backend.dto.event import (
    CreateEventDTO,
    EventDTO,
    LocationDTO,
    ParticipantDTO,
    UpdateEventDTO,
    UserSummaryDTO,
)
from dvizh_backend.dto.invitation import CreateInvitationDTO, InvitationCardDTO, InvitationDTO

from .errors import UserInactiveError, UserNotFoundError
from .notification_service import NotificationService


class EventService:
    """Event and participation rules within one request-scoped database transaction.

    The API works with one occurrence per event: an event is created together with its
    occurrence, and participation is addressed through the earliest occurrence.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.events = EventCRUDService(session)
        self.queries = EventQueryService(session)
        self.participations = ParticipationService(session)
        self.profiles = ProfileService(session)
        self.locations = LocationService(session)
        self.session = session
        self.notifications = NotificationService(session)
        self.engagement = EngagementService(session)
        self.invitations = InvitationService(session)

    async def list_public(
        self,
        *,
        text_query: str | None = None,
        tag: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        free_only: bool = False,
        available_only: bool = False,
        friends_of: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
        viewer_id: UUID | None = None,
    ) -> list[EventDTO]:
        if viewer_id is not None:
            await self._require_active_profile(viewer_id)
        rows = await self.queries.list_public(
            text_query=text_query.strip() if text_query and text_query.strip() else None,
            tag=tag.strip().lower() if tag and tag.strip() else None,
            date_from=date_from,
            date_to=date_to,
            free_only=free_only,
            available_only=available_only,
            friends_of=friends_of,
            offset=offset,
            limit=limit,
            viewer_id=viewer_id,
        )
        return await self._to_dtos(rows, viewer_id=viewer_id)

    async def list_calendar(self, user_id: UUID) -> list[EventDTO]:
        await self._require_active_profile(user_id)
        return await self._to_dtos(await self.queries.list_going(user_id), viewer_id=user_id)

    async def get_event(self, event_id: UUID, viewer_id: UUID | None = None) -> EventDTO:
        if viewer_id is not None:
            await self._require_active_profile(viewer_id)
        row = await self._require_row(event_id)
        if row.event.status == EventStatus.DRAFT and (
            viewer_id is None or not await can_manage_event(self.session, row.event, viewer_id)
        ):
            raise PermissionDeniedError("Draft is only available to its managers")
        return (await self._to_dtos([row], viewer_id=viewer_id))[0]

    async def list_personal(
        self,
        user_id: UUID,
        *,
        kind: Literal["organized", "participating", "requested", "favorites", "dismissed"],
        offset: int = 0,
        limit: int = 20,
    ) -> list[EventDTO]:
        await self._require_active_profile(user_id)
        rows = await self.queries.list_personal(user_id, kind=kind, offset=offset, limit=limit)
        return await self._to_dtos(rows, viewer_id=user_id)

    async def set_favorite(self, event_id: UUID, user_id: UUID, *, enabled: bool) -> EventDTO:
        await self._require_active_profile(user_id)
        await self._require_row(event_id)
        if enabled:
            await self.engagement.add_favorite(user_id, event_id)
        else:
            await self.engagement.remove_favorite(user_id, event_id)
        return await self.get_event(event_id, viewer_id=user_id)

    async def set_dismissed(self, event_id: UUID, user_id: UUID, *, enabled: bool) -> EventDTO:
        await self._require_active_profile(user_id)
        await self._require_row(event_id)
        if enabled:
            await self.engagement.dismiss(user_id, event_id)
        else:
            await self.engagement.undo_dismissal(user_id, event_id)
        return await self.get_event(event_id, viewer_id=user_id)

    async def invite(self, event_id: UUID, data: CreateInvitationDTO) -> InvitationDTO:
        await self._require_active_profile(data.actor_id)
        await self._require_active_profile(data.invitee_id)
        row = await self._require_row(event_id)
        invitation = await self.invitations.invite(
            occurrence_id=row.occurrence.id,
            inviter_user_id=data.actor_id,
            invitee_user_id=data.invitee_id,
            message=data.message,
            expires_at=data.expires_at,
        )
        return InvitationDTO.model_validate(invitation)

    async def list_invitations(
        self, user_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[InvitationCardDTO]:
        await self._require_active_profile(user_id)
        invitations = await self.invitations.list_incoming(user_id, offset=offset, limit=limit)
        rows = await self.queries.get_occurrences([item.occurrence_id for item in invitations])
        dtos = {card.occurrence_id: card for card in await self._to_dtos(rows, viewer_id=user_id)}
        return [
            InvitationCardDTO(
                invitation=InvitationDTO.model_validate(item), event=dtos[item.occurrence_id]
            )
            for item in invitations
            if item.occurrence_id in dtos
        ]

    async def respond_to_invitation(
        self, invitation_id: UUID, user_id: UUID, *, accept: bool
    ) -> InvitationDTO:
        await self._require_active_profile(user_id)
        if accept:
            await self.participations.accept_invitation(invitation_id, user_id)
            invitation = await self.invitations.get(invitation_id)
        else:
            invitation = await self.invitations.decline(invitation_id, user_id)
        return InvitationDTO.model_validate(invitation)

    async def revoke_invitation(self, invitation_id: UUID, actor_id: UUID) -> InvitationDTO:
        await self._require_active_profile(actor_id)
        return InvitationDTO.model_validate(await self.invitations.revoke(invitation_id, actor_id))

    async def create_event(self, data: CreateEventDTO, *, draft: bool = False) -> EventDTO:
        await self._require_active_profile(data.organizer_id)
        location_id = await self._save_location(None, data.location)
        event = Event(
            slug=self._make_slug(data.title),
            origin=EventOrigin.USER,
            status=EventStatus.DRAFT if draft else EventStatus.PUBLISHED,
            published_at=None if draft else datetime.now(UTC),
            organizer_user_id=data.organizer_id,
            created_by_user_id=data.organizer_id,
            location_id=location_id,
            **data.event_columns(),
        )
        occurrence = EventOccurrence(**data.occurrence_columns())
        topic_ids = await self.queries.ensure_topics(data.tags)
        await self.events.create_with_occurrence(event, occurrence, topic_ids=topic_ids)
        return await self.get_event(event.id, viewer_id=data.organizer_id)

    async def list_drafts(
        self, user_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[EventDTO]:
        await self._require_active_profile(user_id)
        return await self._to_dtos(
            await self.queries.list_drafts(user_id, offset=offset, limit=limit), viewer_id=user_id
        )

    async def publish(self, event_id: UUID, actor_id: UUID) -> EventDTO:
        await self._require_active_profile(actor_id)
        await self.events.publish(event_id, actor_id)
        return await self.get_event(event_id, viewer_id=actor_id)

    async def cancel_event(self, event_id: UUID, actor_id: UUID) -> EventDTO:
        await self._require_active_profile(actor_id)
        event = await self.events._get_locked(event_id)
        await self.events._require_manager(event, actor_id)
        if event.status != EventStatus.CANCELLED:
            await self.events.cancel(event_id, actor_id)
            await self.notifications.event_changed(
                event, actor_id, kind="EVENT_CANCELLED", changed_fields=["status"]
            )
        return await self.get_event(event_id, viewer_id=actor_id)

    async def update_event(self, event_id: UUID, data: UpdateEventDTO, actor_id: UUID) -> EventDTO:
        await self._require_active_profile(actor_id)
        locked = await self.events._get_locked(event_id)
        await self.events._require_manager(locked, actor_id)
        if locked.status not in {EventStatus.DRAFT, EventStatus.PUBLISHED}:
            raise InvalidStateTransitionError("Only drafts and published events can be edited")
        before = await self.get_event(event_id, viewer_id=actor_id)
        row = await self._require_row(event_id)
        previous_location_id = row.event.location_id
        location_id = await self._save_location(previous_location_id, data.location)
        for column, value in data.occurrence_columns().items():
            setattr(row.occurrence, column, value)
        await self.events.update(row.event, location_id=location_id, **data.event_columns())
        if location_id is None and previous_location_id is not None:
            await self._delete_location(previous_location_id)
        await self.queries.replace_topics(event_id, await self.queries.ensure_topics(data.tags))
        after = await self.get_event(event_id, viewer_id=actor_id)
        before_data = before.model_dump(mode="json", exclude={"personal_state"})
        after_data = after.model_dump(mode="json", exclude={"personal_state"})
        changed = [key for key, value in before_data.items() if value != after_data[key]]
        if changed and locked.status == EventStatus.PUBLISHED:
            await self.notifications.event_changed(
                locked, actor_id, kind="EVENT_UPDATED", changed_fields=changed
            )
        return after

    async def delete_event(self, event_id: UUID, actor_id: UUID) -> None:
        await self._require_active_profile(actor_id)
        event = await self.events._get_locked(event_id)
        await self.events._require_manager(event, actor_id)
        row = await self._require_row(event_id)
        if event.status == EventStatus.PUBLISHED:
            await self.cancel_event(event_id, actor_id)
        await self.events.update(row.event, deleted_at=datetime.now(UTC))

    async def list_participants(self, event_id: UUID) -> list[ParticipantDTO]:
        row = await self._require_row(event_id)
        participants = await self.queries.list_participants(row.occurrence.id)
        return [
            ParticipantDTO(user=UserSummaryDTO.model_validate(profile), status=participation.status)
            for participation, profile in participants
        ]

    async def join(self, event_id: UUID, user_id: UUID) -> ParticipantDTO:
        row = await self._require_row(event_id)
        profile = await self._require_active_profile(user_id)
        participation = await self.participations.join(row.occurrence.id, user_id)
        return ParticipantDTO(
            user=UserSummaryDTO.model_validate(profile), status=participation.status
        )

    async def review_participation(
        self,
        event_id: UUID,
        user_id: UUID,
        actor_user_id: UUID,
        *,
        accept: bool,
        reason: str | None = None,
    ) -> ParticipantDTO:
        row = await self._require_row(event_id)
        participation = await self.queries.get_participation(row.occurrence.id, user_id)
        if participation is None:
            raise EntityNotFoundError("Participation not found")
        profile = await self._require_profile(user_id)
        participation = await self.participations.decide_request(
            participation.id, actor_user_id, approve=accept, reason=reason
        )
        return ParticipantDTO(
            user=UserSummaryDTO.model_validate(profile), status=participation.status
        )

    async def leave(self, event_id: UUID, user_id: UUID) -> None:
        row = await self._require_row(event_id)
        await self.participations.cancel(row.occurrence.id, user_id)

    async def _require_row(self, event_id: UUID) -> EventRow:
        row = await self.queries.get_primary(event_id)
        if row is None:
            raise EntityNotFoundError("Event not found")
        return row

    async def _require_profile(self, user_id: UUID) -> Profile:
        profile = await self.profiles.get_by_id(user_id)
        if profile is None:
            raise UserNotFoundError("Profile not found")
        return profile

    async def _require_active_profile(self, user_id: UUID) -> Profile:
        profile = await self._require_profile(user_id)
        if profile.status != ProfileStatus.ACTIVE or profile.deleted_at is not None:
            raise UserInactiveError("Profile is not active")
        return profile

    async def _save_location(
        self, location_id: UUID | None, data: LocationDTO | None
    ) -> UUID | None:
        """Create or update the event's own location row; returns its ID, if any."""
        if data is None:
            return None
        location = await self.locations.get_by_id(location_id) if location_id else None
        if location is None:
            return (await self.locations.create(**data.model_dump())).id
        await self.locations.update(location, **data.model_dump())
        return location.id

    async def _delete_location(self, location_id: UUID) -> None:
        location = await self.locations.get_by_id(location_id)
        if location is not None:
            await self.locations.delete(location)

    async def _to_dtos(
        self, rows: list[EventRow], *, viewer_id: UUID | None = None
    ) -> list[EventDTO]:
        if not rows:
            return []
        events = [row.event for row in rows]
        tags = await self.queries.topic_slugs(event.id for event in events)
        locations = await self.queries.locations(
            event.location_id for event in events if event.location_id is not None
        )
        organizers = await self.queries.profiles(
            event.organizer_user_id for event in events if event.organizer_user_id is not None
        )

        dtos = []
        covers = await self.queries.covers(event.id for event in events)
        personal_states = (
            await self.queries.personal_states(viewer_id, rows) if viewer_id is not None else {}
        )
        for row in rows:
            event, occurrence = row.event, row.occurrence
            location = locations.get(event.location_id)
            organizer = organizers.get(event.organizer_user_id)
            dtos.append(
                EventDTO(
                    id=event.id,
                    occurrence_id=occurrence.id,
                    slug=event.slug,
                    title=event.title,
                    description=event.description,
                    tags=tags.get(event.id, []),
                    starts_at=occurrence.starts_at,
                    ends_at=occurrence.ends_at,
                    timezone=occurrence.timezone,
                    is_all_day=occurrence.is_all_day,
                    format=event.format,
                    location=LocationDTO.model_validate(location) if location else None,
                    online_url=event.online_url,
                    registration_url=event.registration_url,
                    price_type=event.price_type,
                    price_min=event.price_min,
                    price_max=event.price_max,
                    currency=event.currency,
                    capacity=event.capacity,
                    participants_count=row.participants_count,
                    status=event.status,
                    visibility=event.visibility,
                    join_policy=event.join_policy,
                    organizer=UserSummaryDTO.model_validate(organizer) if organizer else None,
                    published_at=event.published_at,
                    created_at=event.created_at,
                    cover_media_id=covers.get(event.id),
                    cover_url=(
                        f"/api/media/{covers[event.id]}/content" if event.id in covers else None
                    ),
                    personal_state=personal_states.get(occurrence.id),
                )
            )
        return dtos

    @staticmethod
    def _make_slug(title: str) -> str:
        base = re.sub(r"[^\w]+", "-", title.lower()).strip("-")[:120]
        return f"{base}-{uuid4().hex[:8]}" if base else uuid4().hex
