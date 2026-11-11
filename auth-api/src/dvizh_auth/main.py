from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import uvicorn
from dvizh_logging.http import RequestLoggingMiddleware, configure_http_logging
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, SecretStr

from .config import get_settings
from .database import Database, SessionDep
from .service import authenticate_account, register_account

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


class Application(FastAPI):
    def build_middleware_stack(self) -> RequestLoggingMiddleware:
        return RequestLoggingMiddleware(super().build_middleware_stack())


app = Application(title=settings.app_name, lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-api"}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(
        min_length=settings.password_min_length,
        max_length=128,
    )


class RegisterResponse(BaseModel):
    id: UUID
    email: str


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
        email=str(data.email),
        password=data.password.get_secret_value(),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    return RegisterResponse(id=account.id, email=account.email)


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(max_length=128)


@app.post("/api/auth/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(data: LoginRequest, session: SessionDep) -> Response:
    account = await authenticate_account(
        session,
        email=str(data.email),
        password=data.password.get_secret_value(),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    ttl = settings.access_token_ttl_seconds
    now = datetime.now(timezone.utc)
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

@app.get("/api/auth/me", response_model=RegisterResponse)
async def current_account(request: Request, session: SessionDep) -> RegisterResponse:
    from .models import Account

    try:
        payload = jwt.decode(
            request.cookies.get("dvizh_access", ""),
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        account_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail="Authentication required") from None
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return RegisterResponse(id=account.id, email=account.email)


@app.post("/api/auth/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie("dvizh_access", path="/", httponly=True, samesite="lax")
    return response


if __name__ == "__main__":
    configure_http_logging("auth-api")
    uvicorn.run(app, host="0.0.0.0", port=8003, log_config=None, access_log=False)
