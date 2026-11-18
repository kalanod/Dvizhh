from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.interaction import InteractionDTO

from ..models import Event, EventInteraction, Profile
from ..models.enums import ProfileStatus
from .access import can_view_event
from .exceptions import (
    EntityNotFoundError,
    InteractionConflictError,
    InteractionInputError,
    PermissionDeniedError,
)


class InteractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_batch(
        self, user_id: UUID, interactions: Sequence[InteractionDTO]
    ) -> list[UUID]:
        profile = await self.session.get(Profile, user_id)
        if profile is None:
            raise EntityNotFoundError("Profile not found")
        if profile.status != ProfileStatus.ACTIVE or profile.deleted_at is not None:
            raise PermissionDeniedError("Profile is not active")

        by_id = {interaction.interaction_id: interaction for interaction in interactions}
        existing = await self._get_by_ids(list(by_id))
        for identifier, interaction in by_id.items():
            if identifier in existing:
                self._require_same_payload(existing[identifier], user_id, interaction)

        pending = [by_id[identifier] for identifier in sorted(by_id.keys() - existing.keys())]
        if not pending:
            return list(by_id)

        item_ids = {interaction.item_id for interaction in pending}
        events = await self.session.scalars(select(Event).where(Event.id.in_(item_ids)))
        by_item = {event.id: event for event in events}
        for item_id in item_ids:
            event = by_item.get(item_id)
            if event is None or not await can_view_event(self.session, event, user_id):
                raise InteractionInputError("Interaction item is unavailable")

        statement = insert(EventInteraction).values([
            {
                "interaction_id": interaction.interaction_id,
                "user_id": user_id,
                "event_id": interaction.item_id,
                "type": interaction.event_type,
                "occurred_at": interaction.timestamp,
                "session_id": interaction.session_id,
                "request_id": interaction.request_id,
            }
            for interaction in pending
        ])
        inserted = set(await self.session.scalars(
            statement.on_conflict_do_nothing(index_elements=[EventInteraction.interaction_id])
            .returning(EventInteraction.interaction_id)
        ))
        conflicts = {interaction.interaction_id for interaction in pending} - inserted
        if conflicts:
            stored = await self._get_by_ids(sorted(conflicts))
            for identifier in conflicts:
                if identifier not in stored:
                    raise InteractionConflictError("Interaction was changed concurrently")
                self._require_same_payload(stored[identifier], user_id, by_id[identifier])
        return list(by_id)

    async def _get_by_ids(self, identifiers: list[UUID]) -> dict[UUID, EventInteraction]:
        rows = await self.session.scalars(
            select(EventInteraction).where(EventInteraction.interaction_id.in_(identifiers))
        )
        return {row.interaction_id: row for row in rows if row.interaction_id is not None}

    @staticmethod
    def _require_same_payload(row: EventInteraction, user_id: UUID, dto: InteractionDTO) -> None:
        if (
            row.user_id != user_id
            or row.event_id != dto.item_id
            or row.type != dto.event_type
            or row.occurred_at != dto.timestamp
            or row.session_id != dto.session_id
            or row.request_id != dto.request_id
        ):
            raise InteractionConflictError("Interaction ID already identifies another action")
