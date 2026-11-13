from functools import lru_cache
from secrets import token_urlsafe

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dvizh Auth API"
    database_url: str = "postgresql+asyncpg://dvizh_auth:change-me@localhost:5432/dvizh_auth"
    require_database: bool = False

    jwt_secret: str = Field(default_factory=lambda: token_urlsafe(48), min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "dvizh-auth"
    jwt_audience: str = "dvizh-api"
    access_token_ttl_seconds: int = Field(15 * 60, ge=60, le=24 * 3600)
    access_cookie_secure: bool = False
    refresh_token_ttl_seconds: int = Field(30 * 24 * 3600, ge=3600)

    # Refresh-токен живёт в httpOnly-cookie, видимой только ручкам /api/auth.
    refresh_cookie_name: str = "dvizh_refresh"
    refresh_cookie_path: str = "/api/auth"
    # На http://localhost удобно False; в проде за HTTPS — обязательно True.
    refresh_cookie_secure: bool = False

    password_min_length: int = Field(8, ge=8)
    # argon2 занимает CPU и память; ограничиваем, сколько хешей считается одновременно.
    password_hash_concurrency: int = Field(4, ge=1, le=64)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def secret_or_random(cls, value: str) -> str:
        return value or token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
