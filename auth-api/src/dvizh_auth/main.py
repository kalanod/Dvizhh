from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel

from .config import get_settings
from .database import Database, SessionDep
from .dependencies import require_account, require_account_write
from .dto import LoginRequest, RegisterRequest, UpdateAccountRequest
from .service import AccountConflictError, authenticate_account, register_account, update_account

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = Database(get_settings().database_url)
    try:
        if settings.require_database:
            await database.ping()
        app.state.database = database
        yield
    finally:
        await database.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-api"}


class RegisterResponse(BaseModel):
    id: UUID
    username: str
    email: str | None


@app.post(
    "/api/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
)
async def register(
    data: RegisterRequest,
    session: SessionDep,
) -> RegisterResponse:
    account = await register_account(
        session,
        username=data.username,
        email=str(data.email) if data.email is not None else None,
        password=data.password.get_secret_value(),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered",
        )

    return RegisterResponse(id=account.id, username=account.username, email=account.email)


@app.post("/api/auth/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(data: LoginRequest, session: SessionDep) -> Response:
    account = await authenticate_account(
        session,
        login=str(data.login),
        password=data.password.get_secret_value(),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password",
        )

    ttl = settings.access_token_ttl_seconds
    now = datetime.now(UTC)
    access_token = jwt.encode(
        {
            "sub": str(account.id),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(seconds=ttl),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key="dvizh_access",
        value=access_token,
        max_age=ttl,
        path="/",
        httponly=True,
        secure=settings.access_cookie_secure,
        samesite="lax",
    )
    return response


class CurrentAccountResponse(RegisterResponse):
    role: Literal["user", "admin"]


@app.get("/api/auth/me", response_model=CurrentAccountResponse)
async def current_account(request: Request, session: SessionDep) -> CurrentAccountResponse:
    account = await require_account(request, session)
    return CurrentAccountResponse(
        id=account.id,
        username=account.username,
        email=account.email,
        role=account.role.name,
    )


@app.patch("/api/auth/me", response_model=CurrentAccountResponse)
async def update_current_account(
    data: UpdateAccountRequest,
    request: Request,
    session: SessionDep,
) -> CurrentAccountResponse:
    account = await require_account(request, session)
    require_account_write(request)
    try:
        await update_account(session, account, data.model_dump(exclude_unset=True))
    except AccountConflictError:
        raise HTTPException(
            status_code=409, detail="Username or email is already registered"
        ) from None
    return CurrentAccountResponse(
        id=account.id,
        username=account.username,
        email=account.email,
        role=account.role.name,
    )


@app.post("/api/auth/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie("dvizh_access", path="/", httponly=True, samesite="lax")
    return response
