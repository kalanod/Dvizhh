from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dvizh_backend.database.services.exceptions import (
    CapacityReachedError,
    EntityNotFoundError,
    EventSortError,
    InvalidStateTransitionError,
    InvalidTagSelectionError,
    JoinUnavailableError,
    PermissionDeniedError,
)
from dvizh_backend.services.account_gateway import AccountCommandError
from dvizh_backend.services.discovery_tokens import DiscoveryContextError
from dvizh_backend.services.errors import (
    AvatarUnavailableError,
    FriendshipStateError,
    ProfileAlreadyExistsError,
    UserInactiveError,
    UsernameTakenError,
    UserNotFoundError,
)
from dvizh_backend.services.maps_errors import (
    InvalidPlaceQueryError,
    MapsUnavailableError,
    PlaceNotFoundError,
)
from dvizh_backend.services.media_errors import (
    InvalidImageError,
    MediaTooLargeError,
    MediaUnavailableError,
    StorageUnavailableError,
)
from dvizh_backend.services.settings_service import SettingsActionNotFoundError, SettingsInputError
from dvizh_backend.services.tag_service import CatalogConflictError

STATUS_BY_ERROR: dict[type[Exception], int] = {
    DiscoveryContextError: 409,
    MapsUnavailableError: 503,
    PlaceNotFoundError: 404,
    InvalidPlaceQueryError: 422,
    SettingsInputError: 422,
    EventSortError: 422,
    SettingsActionNotFoundError: 404,
    InvalidImageError: 415,
    CatalogConflictError: 409,
    InvalidTagSelectionError: 422,
    MediaTooLargeError: 413,
    MediaUnavailableError: 409,
    StorageUnavailableError: 503,
    EntityNotFoundError: status.HTTP_404_NOT_FOUND,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    UserInactiveError: status.HTTP_403_FORBIDDEN,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    CapacityReachedError: status.HTTP_409_CONFLICT,
    JoinUnavailableError: status.HTTP_409_CONFLICT,
    ProfileAlreadyExistsError: status.HTTP_409_CONFLICT,
    UsernameTakenError: status.HTTP_409_CONFLICT,
    FriendshipStateError: status.HTTP_409_CONFLICT,
    AvatarUnavailableError: status.HTTP_400_BAD_REQUEST,
}


def register_error_handlers(app: FastAPI) -> None:
    """Translate domain errors of the service layer into HTTP responses."""

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/settings/actions/"):
            return JSONResponse({"detail": "Проверьте формат команды настроек."}, status_code=422)
        if request.url.path == "/api/personal/password" or (
            request.url.path.startswith("/api/admin/users/")
            and request.url.path.endswith("/password")
        ):
            return JSONResponse({"detail": "Invalid password change request"}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(AccountCommandError)
    async def account_command_error(request: Request, exc: AccountCommandError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    def add(error: type[Exception], status_code: int) -> None:
        async def handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc)}, status_code=status_code)

        app.add_exception_handler(error, handler)

    for error, status_code in STATUS_BY_ERROR.items():
        add(error, status_code)
