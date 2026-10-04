from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Event, EventManager, OrganizationMember
from ..models.enums import OrganizationRole


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
