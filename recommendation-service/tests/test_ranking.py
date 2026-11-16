import asyncio
from collections.abc import Sequence

import pytest

from dvizh_recommendation.ranking import (
    DistanceRanker,
    InvalidRankingRequest,
    NoveltyRanker,
    Ranker,
    RankingLayer,
    SqlOrder,
    SqlRanker,
    build_ranking_layer,
)
from dvizh_recommendation.recommendations import RecommendationQuery

QUERY = RecommendationQuery(user_id="user", context={}, filters={})


class ListRanker(Ranker):
    """Ranks a fixed list; records what the base class asked for."""

    def __init__(self, name: str, item_ids: Sequence[str]) -> None:
        self.name = name
        self.item_ids = tuple(item_ids)
        self.requested_limits: list[int] = []

    async def _rank(self, query, *, limit, exclude_ids):
        self.requested_limits.append(limit)
        excluded = set(exclude_ids)
        return [item_id for item_id in self.item_ids if item_id not in excluded][:limit]


@pytest.mark.parametrize(
    ("limit", "error"),
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)],
)
def test_ranker_rejects_invalid_limit(limit, error):
    with pytest.raises(error):
        asyncio.run(ListRanker("list", ()).recommend(QUERY, limit=limit, exclude_ids=()))


def test_ranker_rejects_unsupported_filters():
    query = RecommendationQuery(user_id="user", context={}, filters={"city": "Moscow"})
    with pytest.raises(NotImplementedError):
        asyncio.run(NoveltyRanker(None).recommend(query, limit=100, exclude_ids=()))


def test_ranker_probes_one_extra_item_to_detect_the_end():
    ranker = ListRanker("list", ["a", "b", "c"])

    partial = asyncio.run(ranker.recommend(QUERY, limit=2, exclude_ids=()))
    exact = asyncio.run(ranker.recommend(QUERY, limit=3, exclude_ids=()))
    rest = asyncio.run(ranker.recommend(QUERY, limit=2, exclude_ids=["a", "b"]))

    assert ranker.requested_limits == [3, 4, 3]
    assert partial.item_ids == ("a", "b") and not partial.exhausted
    assert exact.item_ids == ("a", "b", "c") and exact.exhausted
    assert rest.item_ids == ("c",) and rest.exhausted


def test_layer_dispatches_by_name_and_default():
    first, second = ListRanker("first", ["1"]), ListRanker("second", ["2"])
    layer = RankingLayer([first, second], default="second")

    by_default = asyncio.run(layer.recommend(QUERY, limit=5, exclude_ids=()))
    by_name = asyncio.run(
        layer.recommend(
            RecommendationQuery("user", {}, {}, ranking="first"), limit=5, exclude_ids=()
        )
    )

    assert by_default.item_ids == ("2",)
    assert by_name.item_ids == ("1",)
    assert layer.names == ("first", "second")


def test_layer_rejects_unknown_ranking():
    layer = RankingLayer([ListRanker("first", [])], default="first")
    with pytest.raises(InvalidRankingRequest, match="available: first"):
        layer.resolve("popularity")


def test_layer_rejects_duplicate_names_and_unknown_default():
    with pytest.raises(ValueError, match="already registered"):
        RankingLayer([ListRanker("same", []), ListRanker("same", [])], default="same")
    with pytest.raises(ValueError, match="not registered"):
        RankingLayer([ListRanker("first", [])], default="missing")


def test_default_layer_registers_all_rankings():
    layer = build_ranking_layer(None)
    assert layer.names == ("distance", "novelty", "relevance", "title")
    assert layer.default == "novelty"


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"latitude": 59.93},
        {"latitude": "59.93", "longitude": 30.31},
        {"latitude": True, "longitude": 30.31},
        {"latitude": 91, "longitude": 30.31},
        {"latitude": 59.93, "longitude": float("nan")},
    ],
)
def test_distance_requires_valid_coordinates(context):
    query = RecommendationQuery("user", context, {})
    with pytest.raises(InvalidRankingRequest):
        asyncio.run(DistanceRanker(None).order(query, None))


def test_distance_passes_coordinates_as_parameters():
    query = RecommendationQuery("user", {"latitude": 59.93, "longitude": 30}, {})
    order = asyncio.run(DistanceRanker(None).order(query, None))
    assert order.params == (59.93, 30.0)
    assert "59.93" not in order.expression


def test_sql_ranker_numbers_strategy_parameters_after_shared_ones():
    statement = SqlRanker._statement(SqlOrder("f({0}, {1}) DESC", params=(1, 2)))
    assert "f($4, $5) DESC,\n    e.id DESC" in statement
    assert "LIMIT $1" in statement and "ANY($2::uuid[])" in statement
