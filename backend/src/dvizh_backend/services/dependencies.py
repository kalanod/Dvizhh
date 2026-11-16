from typing import Annotated

from fastapi import Depends, Request

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.database.dependencies import DatabaseSession
from dvizh_backend.storage import MediaStorage

from .account_gateway import AccountGateway
from .event_service import EventService
from .feed_service import FeedService
from .media_service import MediaService
from .notification_service import NotificationService
from .recommendation_gateway import RecommendationGateway
from .user_service import UserService


def get_user_service(
    session: DatabaseSession, settings: Annotated[Settings, Depends(get_settings)]
) -> UserService:
    return UserService(session, AccountGateway(settings.auth_url))


def get_event_service(session: DatabaseSession) -> EventService:
    return EventService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_media_storage(request: Request) -> MediaStorage:
    return request.app.state.media_storage


def get_media_service(
    session: DatabaseSession,
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
    settings: SettingsDep,
) -> MediaService:
    return MediaService(session, storage, settings)


def get_notification_service(session: DatabaseSession) -> NotificationService:
    return NotificationService(session)

MediaServiceDep = Annotated[MediaService, Depends(get_media_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]

def get_recommendation_gateway(request: Request) -> RecommendationGateway:
    return request.app.state.recommendations

RecommendationGatewayDep = Annotated[RecommendationGateway, Depends(get_recommendation_gateway)]

def get_feed_service(
    events: EventServiceDep, recommendations: RecommendationGatewayDep
) -> FeedService:
    return FeedService(events, recommendations)


FeedServiceDep = Annotated[FeedService, Depends(get_feed_service)]