from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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

STATUS_BY_ERROR: dict[type[Exception], int] = {
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

    # DTO, собранный в обработчике из уже разобранного запроса, не прошёл валидацию.
    async def invalid_dto(request: Request, exc: ValidationError) -> JSONResponse:
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        return JSONResponse({"detail": errors}, status_code=422)

    app.add_exception_handler(ValidationError, invalid_dto)
