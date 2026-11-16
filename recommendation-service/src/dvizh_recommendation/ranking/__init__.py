"""Ranking layer: the last step before the feed order is stored and paginated.

* ``base.Ranker`` - contract of every strategy;
* ``sql.SqlRanker`` - ordering done by PostgreSQL with ``ORDER BY ... LIMIT``;
* ``strategies`` - concrete rankings;
* ``layer.RankingLayer`` - selects the strategy for a request.
"""

import asyncpg

from .base import InvalidRankingRequest, Ranker
from .layer import RankingLayer
from .sql import SqlOrder, SqlRanker
from .strategies import DistanceRanker, NoveltyRanker, RelevanceRanker, TitleRanker

DEFAULT_RANKING = NoveltyRanker.name


def build_ranking_layer(
    pool: asyncpg.Pool,
    *,
    timeout_seconds: float = 5,
    default: str = DEFAULT_RANKING,
) -> RankingLayer:
    return RankingLayer(
        (
            ranker(pool, timeout_seconds)
            for ranker in (NoveltyRanker, TitleRanker, DistanceRanker, RelevanceRanker)
        ),
        default=default,
    )


__all__ = [
    "DEFAULT_RANKING",
    "DistanceRanker",
    "InvalidRankingRequest",
    "NoveltyRanker",
    "Ranker",
    "RankingLayer",
    "RelevanceRanker",
    "SqlOrder",
    "SqlRanker",
    "TitleRanker",
    "build_ranking_layer",
]