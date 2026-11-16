from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from ..recommendations import RecommendationBatch, RecommendationQuery


class InvalidRankingRequest(ValueError):
    """The request cannot be ranked: unknown strategy or missing/invalid context."""


class Ranker(ABC):
    """Ranking strategy for one feed.

    Every ranker is a ``RecommendationProvider`` and keeps one contract:

    * returns only events available in the catalog and never ``exclude_ids``;
    * returns unique IDs in a deterministic order (ties are broken by event ID);
    * ``exhausted`` is true when nothing ranks after the returned batch.

    The base class owns the contract (validation, ``limit + 1`` probe for
    ``exhausted``); a subclass only decides the order in ``_rank``.
    """

    name: ClassVar[str]

    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch:
        if type(limit) is not int:
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if query.filters:
            raise NotImplementedError("Filters are not implemented")
        item_ids = await self._rank(query, limit=limit + 1, exclude_ids=exclude_ids)
        return RecommendationBatch(
            item_ids=tuple(item_ids[:limit]),
            exhausted=len(item_ids) <= limit,
        )

    @abstractmethod
    async def _rank(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> Sequence[str]:
        """Return at most ``limit`` best event IDs, best first."""