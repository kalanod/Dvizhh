from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    # FastAPI otherwise echoes invalid password inputs in validation responses.
    return JSONResponse(status_code=422, content={"detail": [
        {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
        for item in error.errors()
    ]})
def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error)
