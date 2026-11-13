from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from .config import get_settings


def normalize_text(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def normalize_email(value: object) -> object:
    normalized = normalize_text(value)
    return None if normalized == "" else normalized


Username = Annotated[
    str,
    StringConstraints(min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$"),
    BeforeValidator(normalize_text),
]
OptionalEmail = Annotated[EmailStr | None, BeforeValidator(normalize_email)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    email: OptionalEmail = None
    password: SecretStr = Field(min_length=get_settings().password_min_length, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: Username | Annotated[EmailStr, BeforeValidator(normalize_text)]
    password: SecretStr = Field(max_length=128)


class UpdateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username | None = None
    email: OptionalEmail = None

    @field_validator("username")
    @classmethod
    def username_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Username cannot be null")
        return value

    @model_validator(mode="after")
    def require_fields(self) -> "UpdateAccountRequest":
        if not self.model_fields_set:
            raise ValueError("Provide username or email")
        return self
