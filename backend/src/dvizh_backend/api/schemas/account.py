
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ChangePasswordCommand(BaseModel):
    """Opaque credentials forwarded to auth-api; password policy belongs there."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    current_password: SecretStr = Field(max_length=128)
    new_password: SecretStr = Field(max_length=128)
