from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dvizh_auth.services.account_service import (
    AccountNotFoundError,
    AdminAccessDeniedError,
    SelfDemotionError,
)


async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    # FastAPI otherwise echoes invalid password inputs in validation responses.
    return JSONResponse(status_code=422, content={"detail": [
        {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
        for item in error.errors()
    ]})
def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error)

    def add_handler(error_type: type[Exception], status: int, detail: str) -> None:
        async def handler(request: Request, error: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": detail})

        app.add_exception_handler(error_type, handler)

    for error_type, status, detail in (
        (AccountNotFoundError, 404, "Account not found"),
        (AdminAccessDeniedError, 403, "Administrator access required"),
        (SelfDemotionError, 409, "Cannot remove your own administrator role"),
    ):
        add_handler(error_type, status, detail)
