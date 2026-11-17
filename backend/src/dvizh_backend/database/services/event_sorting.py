"""Порядок ленты событий: каждый способ сортировки — отдельный класс на SQLAlchemy.

Способ задаёт только ключи ``ORDER BY``; фильтры, пагинацию и общий порядок
при равенстве (дата проведения, затем ID) добавляет ``EventQueryService``.
Новый способ: подкласс ``EventSorting`` и его имя в ``EventSort`` и ``SORTINGS``.
"""

import math
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import Float, String, case, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ...dto.event import EventSort
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


class EventSorting(ABC):
    name: ClassVar[EventSort]

    @abstractmethod
    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        """Ключи сортировки, самые подходящие события первыми."""


class NoveltySorting(EventSorting):
    """Сначала недавно опубликованные. Не персональная."""

    name = "novelty"

    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        return [Event.published_at.desc().nulls_last()]


class TitleSorting(EventSorting):
    """По названию от А до Я без учёта регистра. Не персональная."""

    name = "title"

    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        return [func.lower(Event.title), Event.title]


class DistanceSorting(EventSorting):
    """Сначала ближайшие к точке пользователя; онлайн-события в конце.

    Точка — координаты из запроса (геопозиция браузера), а без них — из профиля.
    Расстояние по поверхности Земли считается формулой гаверсинуса.
    """

    name = "distance"
    EARTH_RADIUS_KM: ClassVar[float] = 6371.0088

    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        latitude, longitude = await self._origin(context)
        place_lat = cast(Location.latitude, Float)
        place_lon = cast(Location.longitude, Float)
        origin_lat = literal(latitude, Float)
        origin_lon = literal(longitude, Float)
        half_chord = func.power(func.sin(func.radians(place_lat - origin_lat) / 2.0), 2) + func.cos(
            func.radians(origin_lat)
        ) * func.cos(func.radians(place_lat)) * func.power(
            func.sin(func.radians(place_lon - origin_lon) / 2.0), 2
        )
        # least(1, …) защищает asin от погрешности округления чуть выше 1.
        distance_km = (
            select(2 * self.EARTH_RADIUS_KM * func.asin(func.least(1.0, func.sqrt(half_chord))))
            .where(Location.id == Event.location_id)
            .correlate(Event)
            .scalar_subquery()
        )
        return [distance_km.asc().nulls_last()]

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

    async def order_by(self, context: SortContext) -> list[ColumnElement]:
        interest = await self._interest(context)
        going = (
            select(func.count(EventParticipation.id))
            .where(
                EventParticipation.occurrence_id == EventOccurrence.id,
                EventParticipation.status == ParticipationStatus.GOING,
            )
            .correlate(EventOccurrence)
            .scalar_subquery()
        )
        age_seconds = func.greatest(
            func.extract("epoch", func.now() - func.coalesce(Event.published_at, Event.created_at)),
            0,
        )
        freshness = func.exp(-math.log(2) * age_seconds / (self.FRESHNESS_HALF_LIFE_DAYS * 86400))
        score = (
            self.W_INTEREST * self._interest_score(interest)
            + self.W_POPULAR * func.ln(1 + cast(going, Float))
            + self.W_FRESHNESS * freshness
        )
        return [score.desc(), Event.published_at.desc().nulls_last()]

    @staticmethod
    def _interest_score(interest: Mapping[UUID, float]) -> ColumnElement:
        """Сумма интереса к тегам события, делённая на корень из числа его тегов."""
        if not interest:
            return literal(0.0, Float)
        tag_weight = case(interest, value=EventTag.tag_id, else_=0.0)
        per_event = (
            select(func.sum(tag_weight) / func.sqrt(func.count()))
            .where(EventTag.event_id == Event.id)
            .correlate(Event)
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
        now = datetime.now(UTC)
        weights: dict[UUID, float] = defaultdict(float)
        for tag_id, kind, happened_at in await context.session.execute(signals):
            weight = self.SIGNAL_WEIGHTS.get(kind)
            if weight is None:
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
    for sorting in (NoveltySorting(), TitleSorting(), DistanceSorting(), RelevanceSorting())
}
