from functools import lru_cache
from secrets import token_urlsafe

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dvizh API"
    database_url: str = "postgresql+asyncpg://dvizh:change-me@localhost:5432/dvizh"
    # Если False, приложение стартует и без БД — удобно, чтобы локально открыть Swagger.
    require_database: bool = False
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "dvizh"
    minio_secret_key: str = "change-me-please"
    minio_bucket: str = "media"
    minio_secure: bool = False
    minio_timeout_seconds: float = Field(10, gt=0, le=120)
    media_max_mib: int = Field(10, ge=1, le=128)
    media_max_pixels: int = Field(25_000_000, ge=1, le=100_000_000)
    discovery_token_secret: str = Field(default_factory=lambda: token_urlsafe(48), min_length=32)
    discovery_token_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    recommendation_grpc_address: str = ""
    recommendation_grpc_timeout_seconds: float = Field(2, gt=0, allow_inf_nan=False)

    @field_validator("discovery_token_secret", mode="before")
    @classmethod
    def discovery_default_when_blank(cls, value):
        return token_urlsafe(48) if isinstance(value, str) and not value.strip() else value

    auth_url: str = "http://auth-api:8003"
    yandex_maps_api_key: str = ""
    yandex_suggest_api_key: str = ""
    yandex_geocoder_api_key: str = ""
    yandex_search_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
