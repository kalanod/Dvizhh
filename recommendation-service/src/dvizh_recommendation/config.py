from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dvizh Recommendation Service"
    grpc_bind_address: str = Field(default="0.0.0.0:8001", min_length=1)
    shutdown_grace_seconds: float = Field(default=5, ge=0, allow_inf_nan=False)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
