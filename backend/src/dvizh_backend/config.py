from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dvizh API"
    database_url: str = "postgresql+asyncpg://dvizh:change-me@localhost:5432/dvizh"
    # Если False, приложение стартует и без БД — удобно, чтобы локально открыть Swagger.
    require_database: bool = False
    vector_database_url: str = "postgresql+asyncpg://dvizh:change-me@localhost:5433/dvizh_vectors"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "dvizh"
    minio_secret_key: str = "change-me-please"
    minio_bucket: str = "media"
    recommendation_url: str = "http://recommendation-service:8001"
    auth_url: str = "http://auth-api:8003"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
