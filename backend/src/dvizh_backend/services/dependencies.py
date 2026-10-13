from typing import Annotated

from fastapi import Depends

from dvizh_backend.database.dependencies import DatabaseSession

from .event_service import EventService
from .user_service import UserService


def get_user_service(session: DatabaseSession) -> UserService:
    return UserService(session)


def get_event_service(session: DatabaseSession) -> EventService:
    return EventService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
