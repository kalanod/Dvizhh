from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_RANKER_MODEL_DIR = Path("/models")


class Settings(BaseSettings):
    app_name: str = "Dvizh Recommendation Service"
    source_database_url: SecretStr = Field(min_length=1)
    vector_database_url: SecretStr = Field(min_length=1)
    ranker_model_dir: Path = DEFAULT_RANKER_MODEL_DIR
    ranker_model_uri: str | None = None
    previous_ranker_model_uri: str | None = None
    vector_model_id: str | None = None
    previous_vector_model_id: str | None = None
    redis_url: SecretStr = Field(min_length=1)
    redis_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    recommendation_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    grpc_bind_address: str = Field(default="0.0.0.0:8001", min_length=1)
    shutdown_grace_seconds: float = Field(default=5, ge=0, allow_inf_nan=False)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def validate_pool_size(self) -> Self:
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("database_pool_min_size must not exceed database_pool_max_size")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
