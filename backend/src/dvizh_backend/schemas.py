import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import JoinMode, ParticipationStatus, Visibility


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, description="Уникальное имя пользователя.")
    display_name: str = Field(min_length=1, max_length=100, description="Отображаемое имя.")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str


class EventUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Название события.")
    description: str | None = Field(None, description="Описание события.")
    tags: list[str] = Field(default_factory=list, description="Тематики (теги) события.")

    start_date: date = Field(description="Дата начала (обязательна).")
    start_time: time | None = Field(
        None, description="Время начала; не указано — событие на весь день."
    )
    end_date: date | None = Field(
        None, description="Дата окончания для событий, идущих несколько дней."
    )
    end_time: time | None = Field(None, description="Время окончания.")

    is_online: bool = Field(False, description="Онлайн-событие.")
    place: str | None = Field(None, description="Место проведения для офлайн-события.")
    link: str | None = Field(
        None,
        description=(
            "Ссылка: на трансляцию онлайн-события либо на внешнюю регистрацию или покупку билетов."
        ),
    )

    price: Decimal | None = Field(
        None,
        ge=0,
        le=100_000_000,
        decimal_places=2,
        description="Стоимость участия; не указана или 0 — бесплатно.",
    )
    max_participants: int | None = Field(
        None, ge=1, description="Максимальное количество участников; не указано — без лимита."
    )

    visibility: Visibility = Field(
        Visibility.PUBLIC,
        description=(
            "Видимость: public — в общей ленте, friends — друзьям организатора, "
            "unlisted — только по прямой ссылке, private — только приглашённым."
        ),
    )
    join_mode: JoinMode = Field(
        JoinMode.OPEN,
        description=(
            "Способ вступления: open — сразу участник, request — заявка организатору, "
            "invite_only — по приглашению, external — во внешней системе."
        ),
    )

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Дата окончания не может быть раньше даты начала.")
        same_day = self.end_date is None or self.end_date == self.start_date
        if (
            same_day
            and self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("Время окончания не может быть раньше времени начала.")
        return self

    def to_columns(self) -> dict:
        data = self.model_dump()
        data["title"] = self.title.strip()
        data["tags"] = list(dict.fromkeys(t.strip().lower() for t in self.tags if t.strip()))
        data["price"] = self.price or None
        return data


class EventCreate(EventUpdate):
    organizer_id: uuid.UUID = Field(
        description="Идентификатор организатора (пока нет авторизации, передаётся явно)."
    )


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    tags: list[str]
    start_date: date
    start_time: time | None
    end_date: date | None
    end_time: time | None
    is_online: bool
    place: str | None
    link: str | None
    price: Decimal | None
    max_participants: int | None
    participants_count: int = Field(description="Сколько пользователей идёт на событие.")
    visibility: Visibility
    join_mode: JoinMode
    organizer: UserResponse
    created_at: datetime


class JoinRequest(BaseModel):
    user_id: uuid.UUID = Field(description="Идентификатор пользователя, который хочет пойти.")


class ReviewRequest(BaseModel):
    accept: bool = Field(description="true — принять заявку, false — отклонить.")


class ParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserResponse
    status: ParticipationStatus
