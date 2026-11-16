from collections.abc import Iterable, Sequence

from ..recommendations import RecommendationBatch, RecommendationQuery
from .base import InvalidRankingRequest, Ranker


class RankingLayer:
    """The only ``RecommendationProvider`` pagination talks to.

    It owns one decision: which registered strategy ranks this request
    (``query.ranking`` or the default). It does not order, filter or paginate.
    A new ranking is added by implementing ``Ranker`` and registering it.
    """

    def __init__(self, rankers: Iterable[Ranker], *, default: str) -> None:
        self._rankers: dict[str, Ranker] = {}
        for ranker in rankers:
            self.register(ranker)
        if default not in self._rankers:
            raise ValueError(f"Default ranking {default!r} is not registered")
        self.default = default

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._rankers))

    def register(self, ranker: Ranker) -> None:
        if ranker.name in self._rankers:
            raise ValueError(f"Ranking {ranker.name!r} is already registered")
        self._rankers[ranker.name] = ranker

    def resolve(self, name: str | None) -> Ranker:
        ranker = self._rankers.get(self.default if name is None else name)
        if ranker is None:
            raise InvalidRankingRequest(
                f"Unknown ranking {name!r}; available: {', '.join(self.names)}"
            )
        return ranker

    async def recommend(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[str],
    ) -> RecommendationBatch:
        return await self.resolve(query.ranking).recommend(
            query, limit=limit, exclude_ids=exclude_ids
        )