from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.services.account_context import AccountRequestContext
from dvizh_backend.services.account_gateway import AccountGateway
from dvizh_backend.services.event_service import EventService
from dvizh_backend.services.maps_service import MapsService
from dvizh_backend.services.media_service import MediaService
from dvizh_backend.services.notification_service import NotificationService
from dvizh_backend.services.settings_service import SettingsService
from dvizh_backend.services.tag_service import TagService
from dvizh_backend.services.user_service import UserService
from dvizh_backend.storage import MediaStorage


def get_database_service(request: Request) -> DatabaseService:
    return request.app.state.database_service


async def get_db_session(
    database_service: Annotated[DatabaseService, Depends(get_database_service)],
) -> AsyncIterator[AsyncSession]:
    async with database_service.session() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]


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


def get_tag_service(session: DatabaseSession) -> TagService:
    return TagService(session)


TagServiceDep = Annotated[TagService, Depends(get_tag_service)]


def get_settings_service(tags: TagServiceDep, users: UserServiceDep) -> SettingsService:
    return SettingsService(tags, users)


SettingsServiceDep = Annotated[SettingsService, Depends(get_settings_service)]


def get_maps_service(settings: SettingsDep) -> MapsService:
    return MapsService(settings)


MapsServiceDep = Annotated[MapsService, Depends(get_maps_service)]


def get_timezone_service(users: UserServiceDep, settings: SettingsDep, request: Request):
    from dvizh_backend.services.event_timezone_service import EventTimezoneService
    from dvizh_backend.services.place_geocoding import ProfileCityGeocoder

    return EventTimezoneService(users, ProfileCityGeocoder(
        settings.yandex_geocoder_api_key or settings.yandex_maps_api_key,
        request.headers.get("referer", str(request.base_url)),
    ))


def get_account_context(request: Request) -> AccountRequestContext:
    return AccountRequestContext(
        token=request.cookies.get("dvizh_access", ""),
        host=request.headers.get("host", ""),
        origin=request.headers.get("origin"),
        write_header=request.headers.get("x-dvizh-account", ""),
    )


AccountContextDep = Annotated[AccountRequestContext, Depends(get_account_context)]


async def get_discovery_viewer(request: Request):
    """Optional verified identity for personalized public discovery, never a body/query UUID."""
    token = request.cookies.get("dvizh_access")
    if not token:
        return None
    import asyncio

    from dvizh_backend.services.account_gateway import fetch_current_account
    account = await asyncio.to_thread(fetch_current_account, get_settings().auth_url, token)
    return account.id


async def get_discovery_service(session: DatabaseSession, settings: SettingsDep):
    from dvizh_backend.database.services.discovery import DiscoveryRepository
    from dvizh_backend.services.discovery_service import EventDiscoveryService
    await DiscoveryRepository.begin_snapshot(session)
    return EventDiscoveryService(session, settings)
