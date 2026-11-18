from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AdminUserDTO(BaseModel):
    id: UUID
    username: str
    email: str | None
    role: Literal["user", "admin"]


class AdminUserPage(BaseModel):
    items: list[AdminUserDTO]
    offset: int
    limit: int
    has_more: bool


class ChangeRoleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "admin"]


class ResetPasswordCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: SecretStr = Field(min_length=8, max_length=128)
