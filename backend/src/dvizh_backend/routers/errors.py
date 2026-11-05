from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ..database.services.exceptions import (
    CapacityReachedError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    JoinUnavailableError,
    PermissionDeniedError,
)
from ..services.errors import (
    AvatarUnavailableError,
    FriendshipStateError,
    ProfileAlreadyExistsError,
    UserInactiveError,
    UsernameTakenError,
    UserNotFoundError,
)
from ..services.media_errors import (
    InvalidImageError,
    MediaTooLargeError,
    MediaUnavailableError,
    StorageUnavailableError,
)

STATUS_BY_ERROR: dict[type[Exception], int] = {
    InvalidImageError: 415,
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

    def add(error: type[Exception], status_code: int) -> None:
        async def handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc)}, status_code=status_code)

        app.add_exception_handler(error, handler)

    for error, status_code in STATUS_BY_ERROR.items():
        add(error, status_code)
