"""Порядок ленты событий: каждый способ сортировки — отдельный класс на SQLAlchemy.

Способ задаёт типизированные ключи порядка для обычной и курсорной выдачи;
фильтры и общий порядок при равенстве добавляет репозиторий.
Новый способ: подкласс ``EventSorting`` и его имя в ``EventSort`` и ``SORTINGS``.
"""

import math
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from sqlalchemy import Float, String, case, cast, false, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from dvizh_backend.api.schemas.event import EventSort
from dvizh_backend.database.geo import GeographyPoint

from ..models import (
    Event,
    EventDismissal,
    EventFavorite,
    EventInteraction,
    EventOccurrence,
    EventParticipation,
    EventTag,
    Location,
    Profile,
)
from ..models.enums import InteractionType, ParticipationStatus
from .exceptions import EventSortError


@dataclass(frozen=True)
class SortContext:
    session: AsyncSession
    viewer_id: UUID | None
    latitude: float | None
    longitude: float | None
    as_of: datetime = field(default_factory=lambda: datetime.now(UTC))
    columns: Any = None
    interest: Mapping[UUID, float] | None = None

    def event_column(self, name: str) -> ColumnElement:
        if self.columns is None:
            return getattr(Event, name)
        return getattr(self.columns, "event_id" if name == "id" else name)


@dataclass(frozen=True)
class SortKey:
    """One ORDER BY key, including the matching cursor comparison and value type."""

    expression: ColumnElement
    kind: Literal["number", "text", "datetime", "uuid"] = "number"
    descending: bool = False

    def order_by(self) -> ColumnElement:
        ordered = self.expression.desc() if self.descending else self.expression.asc()
        return ordered.nulls_last()

    def decode(self, value):
        if value is None:
            return None
        if self.kind == "datetime":
            return datetime.fromisoformat(value)
        if self.kind == "uuid":
            return UUID(value)
        if self.kind == "text":
            if not isinstance(value, str):
                raise ValueError("Invalid text cursor")
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Invalid numeric cursor")
        if not math.isfinite(value):
            raise ValueError("Invalid numeric cursor")
        return value

    def encode(self, value):
        if value is None:
            return None
        if self.kind == "datetime":
            return value.isoformat()
        if self.kind in {"uuid", "text"}:
            return str(value)
        return float(value)

    def equal_to(self, value) -> ColumnElement:
        return self.expression.is_(None) if value is None else self.expression == value

    def after(self, value) -> ColumnElement:
        if value is None:
            return false()  # NULLS LAST: only subsequent tie-breakers can follow a null key.
        comparison = self.expression < value if self.descending else self.expression > value
        return or_(comparison, self.expression.is_(None))


class EventSorting(ABC):
    name: ClassVar[EventSort]

    @abstractmethod
    async def keys(self, context: SortContext) -> list[SortKey]:
        """Ключи сортировки, самые подходящие события первыми."""

    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        return [key.order_by() for key in await self.keys(context)]


class NoveltySorting(EventSorting):
    """Сначала недавно опубликованные. Не персональная."""

    name = "novelty"

    async def keys(self, context: SortContext) -> list[SortKey]:
        return [SortKey(context.event_column("published_at"), "datetime", descending=True)]


class TitleSorting(EventSorting):
    """По названию от А до Я без учёта регистра. Не персональная."""

    name = "title"

    async def keys(self, context: SortContext) -> list[SortKey]:
        title = context.event_column("title")
        return [SortKey(func.lower(title), "text"), SortKey(title, "text")]


class StartSorting(EventSorting):
    name = "start"

    async def keys(self, context: SortContext) -> list[SortKey]:
        starts = (
            context.columns.starts_at if context.columns is not None else EventOccurrence.starts_at
        )
        return [SortKey(starts, "datetime")]


class DistanceSorting(EventSorting):
    """Сначала ближайшие к точке пользователя; онлайн-события в конце.

    Точка — координаты из запроса (геопозиция браузера), а без них — из профиля.
    Расстояние по поверхности Земли считается PostGIS в метрах.
    """

    name = "distance"

    async def keys(self, context: SortContext) -> list[SortKey]:
        latitude, longitude = await self._origin(context)
        origin = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        position = context.columns.position if context.columns is not None else Location.position
        distance = func.ST_Distance(
            cast(position, GeographyPoint()), cast(origin, GeographyPoint())
        )
        if context.columns is None:
            distance = (
                select(distance)
                .where(Location.id == Event.location_id)
                .correlate(Event)
                .scalar_subquery()
            )
        return [SortKey(cast(distance, Float))]

    @staticmethod
    async def _origin(context: SortContext) -> tuple[float, float]:
        if context.latitude is not None and context.longitude is not None:
            return context.latitude, context.longitude
        if context.latitude is not None or context.longitude is not None:
            raise EventSortError("Передайте latitude и longitude вместе.")
        profile = (
            await context.session.get(Profile, context.viewer_id)
            if context.viewer_id is not None
            else None
        )
        if profile is None or profile.latitude is None or profile.longitude is None:
            raise EventSortError(
                "Чтобы показать события рядом, разрешите доступ к геопозиции "
                "или укажите широту и долготу в профиле."
            )
        return float(profile.latitude), float(profile.longitude)


class RelevanceSorting(EventSorting):
    """Персональная лента: интерес к тематикам события, популярность и свежесть.

    Интерес — вес тега по действиям пользователя с затуханием по времени.
    Без истории остаются популярность и свежесть: это запасной вариант,
    а не персонализация.
    """

    name = "relevance"

    SIGNAL_WEIGHTS: ClassVar[Mapping[str, float]] = {
        "GOING": 4.0,
        "REQUESTED": 3.0,
        "FAVORITE": 3.0,
        "JOIN_CLICK": 2.0,
        "EXTERNAL_LINK_CLICK": 2.0,
        "OPEN": 1.0,
        "CANCELLED": -1.0,
        "DISMISSED": -4.0,
    }
    SIGNAL_HALF_LIFE_DAYS: ClassVar[float] = 30
    PROFILE_TAG_LIMIT: ClassVar[int] = 50
    W_INTEREST: ClassVar[float] = 1.0
    W_POPULAR: ClassVar[float] = 0.15
    W_FRESHNESS: ClassVar[float] = 0.3
    FRESHNESS_HALF_LIFE_DAYS: ClassVar[float] = 14

    async def keys(self, context: SortContext) -> list[SortKey]:
        interest = (
            context.interest if context.interest is not None else await self._interest(context)
        )
        going = (
            context.columns.going_count
            if context.columns is not None
            else (
                select(func.count(EventParticipation.id))
                .where(
                    EventParticipation.occurrence_id == EventOccurrence.id,
                    EventParticipation.status == ParticipationStatus.GOING,
                )
                .correlate(EventOccurrence)
                .scalar_subquery()
            )
        )
        age_seconds = func.greatest(
            func.extract(
                "epoch",
                literal(context.as_of)
                - func.coalesce(
                    context.event_column("published_at"),
                    context.event_column("created_at"),
                ),
            ),
            0,
        )
        freshness = func.exp(-math.log(2) * age_seconds / (self.FRESHNESS_HALF_LIFE_DAYS * 86400))
        score = (
            self.W_INTEREST * self._interest_score(interest, context)
            + self.W_POPULAR * func.ln(1 + cast(going, Float))
            + self.W_FRESHNESS * freshness
        )
        return [
            SortKey(cast(score, Float), descending=True),
            SortKey(context.event_column("published_at"), "datetime", descending=True),
        ]

    @staticmethod
    def _interest_score(interest: Mapping[UUID, float], context: SortContext) -> ColumnElement:
        """Сумма интереса к тегам события, делённая на корень из числа его тегов."""
        if not interest:
            return literal(0.0, Float)
        tag_weight = case(interest, value=EventTag.tag_id, else_=0.0)
        per_event = (
            select(func.sum(tag_weight) / func.sqrt(func.count()))
            .where(EventTag.event_id == context.event_column("id"))
            .correlate(context.columns.event_id.table if context.columns is not None else Event)
            .scalar_subquery()
        )
        return func.coalesce(per_event, 0.0)

    async def _interest(self, context: SortContext) -> dict[UUID, float]:
        """Вес тега по сигналам пользователя, нормированный в [-1, 1]; пусто без истории."""
        user_id = context.viewer_id
        if user_id is None:
            return {}
        signals = union_all(
            select(
                EventTag.tag_id,
                literal("FAVORITE", String).label("kind"),
                EventFavorite.created_at.label("happened_at"),
            )
            .join(EventTag, EventTag.event_id == EventFavorite.event_id)
            .where(EventFavorite.user_id == user_id),
            select(
                EventTag.tag_id,
                cast(EventParticipation.status, String),
                EventParticipation.updated_at,
            )
            .join(EventOccurrence, EventOccurrence.id == EventParticipation.occurrence_id)
            .join(EventTag, EventTag.event_id == EventOccurrence.event_id)
            .where(EventParticipation.user_id == user_id),
            select(EventTag.tag_id, literal("DISMISSED", String), EventDismissal.created_at)
            .join(EventTag, EventTag.event_id == EventDismissal.event_id)
            .where(EventDismissal.user_id == user_id),
            select(
                EventTag.tag_id,
                cast(EventInteraction.type, String),
                EventInteraction.occurred_at,
            )
            .join(EventTag, EventTag.event_id == EventInteraction.event_id)
            .where(
                EventInteraction.user_id == user_id,
                EventInteraction.type.in_(
                    [
                        InteractionType.OPEN,
                        InteractionType.JOIN_CLICK,
                        InteractionType.EXTERNAL_LINK_CLICK,
                    ]
                ),
            ),
        )
        now = context.as_of
        weights: dict[UUID, float] = defaultdict(float)
        for tag_id, kind, happened_at in await context.session.execute(signals):
            weight = self.SIGNAL_WEIGHTS.get(kind)
            if weight is None:
                continue
            if happened_at > now:
                continue
            age_days = max((now - happened_at).total_seconds(), 0) / 86400
            weights[tag_id] += weight * 0.5 ** (age_days / self.SIGNAL_HALF_LIFE_DAYS)

        strongest = sorted(
            ((tag, weight) for tag, weight in weights.items() if weight != 0),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[: self.PROFILE_TAG_LIMIT]
        if not strongest:
            return {}
        scale = max(abs(weight) for _, weight in strongest)
        return {tag: weight / scale for tag, weight in strongest}


SORTINGS: dict[EventSort, EventSorting] = {
    sorting.name: sorting
    for sorting in (
        NoveltySorting(),
        TitleSorting(),
        DistanceSorting(),
        RelevanceSorting(),
        StartSorting(),
    )
}
