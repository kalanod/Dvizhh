from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from dvizh_backend.database.models.enums import (
    EventFormat,
    EventJoinPolicy,
    EventPriceType,
    EventStatus,
    EventVisibility,
    ParticipationStatus,
)


class UserSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str


class LocationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    name: str | None = Field(None, max_length=200, description="Название места.")
    city: str | None = Field(None, max_length=120, description="Город.")
    address_line: str | None = Field(None, description="Адрес.")
    latitude: Decimal = Field(ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, max_digits=9, decimal_places=6)


class UpdateEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="Название события.")
    description: str = Field("", description="Описание события.")
    tags: list[str] = Field(default_factory=list, description="Тематики (теги) события.")

    starts_at: AwareDatetime = Field(description="Начало события (с часовым поясом).")
    ends_at: AwareDatetime | None = Field(None, description="Окончание события.")
    timezone: str = Field(
        "Europe/Moscow", max_length=64, description="Часовой пояс события (IANA)."
    )
    is_all_day: bool = Field(False, description="Событие на весь день.")

    format: EventFormat = Field(
        EventFormat.OFFLINE,
        description=(
            "Формат: OFFLINE — нужно место, ONLINE — нужна ссылка на трансляцию, "
            "HYBRID — нужно и то и другое."
        ),
    )
    location: LocationDTO | None = Field(None, description="Место проведения.")
    online_url: str | None = Field(None, description="Ссылка на трансляцию.")
    registration_url: str | None = Field(
        None, description="Ссылка на внешнюю регистрацию или покупку билетов."
    )

    price_min: Decimal | None = Field(
        None,
        ge=0,
        le=100_000_000,
        decimal_places=2,
        description="Стоимость участия (нижняя граница); не указана или 0 — бесплатно.",
    )
    price_max: Decimal | None = Field(
        None,
        ge=0,
        le=100_000_000,
        decimal_places=2,
        description="Верхняя граница стоимости, если цена задана диапазоном.",
    )
    currency: str = Field("RUB", pattern=r"^[A-Z]{3}$", description="Валюта платного события.")
    capacity: int | None = Field(
        None, ge=1, description="Максимальное количество участников; не указано — без лимита."
    )

    visibility: EventVisibility = Field(
        EventVisibility.PUBLIC,
        description=(
            "Видимость: PUBLIC — в общей ленте, FRIENDS — друзьям организатора, "
            "UNLISTED — только по прямой ссылке, PRIVATE — только приглашённым."
        ),
    )
    join_policy: EventJoinPolicy = Field(
        EventJoinPolicy.OPEN,
        description=(
            "Способ вступления: OPEN — сразу участник, REQUEST — заявка организатору, "
            "INVITE_ONLY — по приглашению, EXTERNAL — во внешней системе."
        ),
    )

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым.")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        tags = list(dict.fromkeys(tag.strip().lower() for tag in value if tag.strip()))
        if any(len(tag) > 80 for tag in tags):
            raise ValueError("Тег не может быть длиннее 80 символов.")
        return tags

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Неизвестный часовой пояс.") from exc
        return value

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("Окончание должно быть позже начала.")

        needs_location = self.format != EventFormat.ONLINE
        needs_online_url = self.format != EventFormat.OFFLINE
        if needs_location != (self.location is not None):
            raise ValueError("Место указывается для форматов OFFLINE и HYBRID и только для них.")
        if needs_online_url != (self.online_url is not None):
            raise ValueError(
                "Ссылка на трансляцию указывается для форматов ONLINE и HYBRID и только для них."
            )

        if not self.price_min and self.price_max is not None:
            raise ValueError("Верхняя граница цены задаётся только вместе с нижней.")
        if self.price_min and self.price_max is not None and self.price_max < self.price_min:
            raise ValueError("Верхняя граница цены не может быть меньше нижней.")
        return self

    def event_columns(self) -> dict[str, Any]:
        is_paid = bool(self.price_min)
        return {
            "title": self.title,
            "description": self.description,
            "format": self.format,
            "online_url": self.online_url,
            "registration_url": self.registration_url,
            "price_type": EventPriceType.PAID if is_paid else EventPriceType.FREE,
            "price_min": self.price_min if is_paid else None,
            "price_max": self.price_max if is_paid else None,
            "currency": self.currency if is_paid else None,
            "capacity": self.capacity,
            "visibility": self.visibility,
            "join_policy": self.join_policy,
        }

    def occurrence_columns(self) -> dict[str, Any]:
        return {
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "timezone": self.timezone,
            "is_all_day": self.is_all_day,
        }


class CreateEventDTO(UpdateEventDTO):
    organizer_id: UUID = Field(
        description="Идентификатор организатора (пока нет авторизации, передаётся явно)."
    )


class EventDTO(BaseModel):
    id: UUID
    occurrence_id: UUID = Field(description="Проведение события, к которому относятся участия.")
    slug: str
    title: str
    description: str
    tags: list[str]
    starts_at: datetime
    ends_at: datetime | None
    timezone: str
    is_all_day: bool
    format: EventFormat
    location: LocationDTO | None
    online_url: str | None
    registration_url: str | None
    price_type: EventPriceType
    price_min: Decimal | None
    price_max: Decimal | None
    currency: str | None
    capacity: int | None
    participants_count: int = Field(description="Сколько пользователей идёт на событие.")
    status: EventStatus
    visibility: EventVisibility
    join_policy: EventJoinPolicy
    organizer: UserSummaryDTO | None
    published_at: datetime | None
    created_at: datetime


class JoinEventDTO(BaseModel):
    user_id: UUID = Field(description="Идентификатор пользователя, который хочет пойти.")


class ReviewParticipationDTO(BaseModel):
    actor_id: UUID = Field(
        description=(
            "Кто рассматривает заявку: организатор или менеджер события "
            "(пока нет авторизации, передаётся явно)."
        )
    )
    accept: bool = Field(description="true — принять заявку, false — отклонить.")
    reason: str | None = Field(None, max_length=500, description="Причина отказа.")


class ParticipantDTO(BaseModel):
    user: UserSummaryDTO
    status: ParticipationStatus
