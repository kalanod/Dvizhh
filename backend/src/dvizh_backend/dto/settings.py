"""Version 2 of the server-driven settings UI protocol."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextElement(SettingsModel):
    id: str
    type: Literal["text"] = "text"
    text: str
    tone: Literal["normal", "muted"] = "normal"


class InputElement(SettingsModel):
    id: str
    type: Literal["input"] = "input"
    label: str
    value: str = ""
    input_type: Literal["text", "password"] = "text"
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    hint: str | None = None
    matches: str | None = None
    autocomplete: str | None = None


class SelectOption(SettingsModel):
    value: str
    label: str


class SelectElement(SettingsModel):
    id: str
    type: Literal["select"] = "select"
    label: str
    value: str
    options: list[SelectOption]
    required: bool = True


class ToggleElement(SettingsModel):
    id: str
    type: Literal["toggle"] = "toggle"
    label: str
    value: bool
    hint: str | None = None


class ButtonElement(SettingsModel):
    id: str
    type: Literal["button"] = "button"
    label: str
    action_id: str
    tone: Literal["primary", "secondary", "danger"] = "primary"
    validate_fields: bool = True
    confirmation: str | None = None
    rows: Literal["all", "changed"] = "all"


SettingElement = Annotated[
    TextElement | InputElement | SelectElement | ToggleElement | ButtonElement,
    Field(discriminator="type"),
]


class SettingsRow(SettingsModel):
    id: str
    elements: list[SettingElement]


class SettingsCard(SettingsModel):
    id: str
    title: str | None = None
    description: str | None = None
    rows: list[SettingsRow]
    actions: list[ButtonElement] = Field(default_factory=list)


class SettingsTab(SettingsModel):
    id: str
    label: str
    cards: list[SettingsCard]


class SettingsDocument(SettingsModel):
    schema_version: Literal[2] = 2
    tabs: list[SettingsTab]


class SettingsActionRequest(SettingsModel):
    schema_version: Literal[2]
    rows: dict[str, Annotated[dict[str, StrictStr | StrictBool], Field(max_length=30)]] = Field(
        max_length=500, repr=False
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def supported_version(cls, value: object) -> int:
        if type(value) is not int or value != 2:
            raise ValueError("Unsupported settings schema version")
        return value


class SettingsActionResponse(SettingsModel):
    schema_version: Literal[2] = 2
    message: str
    document: SettingsDocument
    applied_rows: list[str]
