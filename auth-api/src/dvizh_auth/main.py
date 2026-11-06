from contextlib import asynccontextmanager

from .config import get_settings

from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, SecretStr

from .database import Database, SessionDep
from .service import register_account

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