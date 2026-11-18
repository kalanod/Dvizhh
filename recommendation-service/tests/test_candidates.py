import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from dvizh_recommendation.candidates import RecommendationPipeline, RetrievalScoreRanker
from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import Databases
from dvizh_recommendation.hnsw import HnswCandidates
from dvizh_recommendation.pipelines import PipelineFactory
from dvizh_recommendation.recommendations import (
    Candidate,
    CandidateBatch,
    NoUserVector,
    RecommendationQuery,
)


def test_recommendations_reject_unsupported_filters():
    async def check():
        provider = RecommendationPipeline(None)
        query = RecommendationQuery(user_id="user", context={}, filters={"city": "Moscow"})
        with pytest.raises(NotImplementedError):
            await provider.recommend(query, limit=100, exclude_ids=())

    asyncio.run(check())


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> tuple[UUID, ...]:
    items = tuple(uuid4() for _ in range(3))
    now = datetime.now(UTC)
    rows = [
        {
            "item_id": item_id,
            "occurrence_id": uuid4(),
            "starts_at": now,
            "published_at": now,
            "participants_count": 0,
            "price_type": "FREE",
            "format": "ONLINE",
            "join_policy": "OPEN",
        }
        for item_id in items
    ]
    monkeypatch.setattr(
        "dvizh_recommendation.candidates.catalog_items", AsyncMock(return_value=rows)
    )
    return items


def source(name: str, *candidates: Candidate, failure: Exception | None = None):
    return SimpleNamespace(
        name=name,
        generate=AsyncMock(return_value=CandidateBatch(candidates, True), side_effect=failure),
    )


def recommend(*sources):
    pipeline = RecommendationPipeline(
        None, generators=sources, ranker=RetrievalScoreRanker("hnsw"), version="test",
    )
    return asyncio.run(
        pipeline.recommend(RecommendationQuery(str(uuid4()), {}, {}), limit=100, exclude_ids=())
    )


def test_hnsw_scores_order_merged_items_and_follow_them_into_snapshots(catalog):
    near, far, popular_only = catalog
    page = recommend(
        source("popular", Candidate(popular_only, 999), Candidate(far, 500)),
        source("hnsw", Candidate(far, -0.2), Candidate(near, 0.8)),
    )

    assert page.item_ids == tuple(map(str, (near, far, popular_only)))
    assert [item.features["hnsw_score"] for item in page.snapshots] == [0.8, -0.2, None]


@pytest.mark.parametrize("failure", [None, NoUserVector()], ids=["empty", "missing-user-vector"])
def test_other_sources_can_serve_when_hnsw_has_no_candidates(catalog, failure):
    page = recommend(source("hnsw", failure=failure), source("popular", Candidate(catalog[0], 8)))
    assert page.item_ids == (str(catalog[0]),)
    assert page.exhausted


def test_source_database_error_is_propagated(catalog):
    with pytest.raises(ConnectionError):
        recommend(
            source("hnsw", failure=ConnectionError()), source("popular", Candidate(catalog[0]))
        )


def test_session_restores_its_configured_sources_after_an_index_update(catalog, monkeypatch):
    popular = source("popular", Candidate(catalog[1]))
    monkeypatch.setattr(HnswCandidates, "check_ready", AsyncMock(return_value=True))

    async def from_index(generator, query, **kwargs):
        item_id = {"index-1": catalog[0], "index-2": catalog[2]}[generator.revision]
        return CandidateBatch((Candidate(item_id, 1),), True)

    monkeypatch.setattr(HnswCandidates, "generate", from_index)
    settings = Settings(
        source_database_url="postgresql://catalog", vector_database_url="postgresql://vectors",
        redis_url="redis://cache", _env_file=None,
    )

    def factory(*sources):
        return PipelineFactory(Databases(None, None), settings, additional_generators=sources)

    async def check():
        query = RecommendationQuery(str(uuid4()), {}, {})
        configured = factory((popular, "v1"))
        original = await configured.load(None, "encoder", "index-1")
        standalone = await configured.load(None, None, None)
        page = await standalone.recommend(query, limit=100, exclude_ids=())
        assert page.item_ids == (str(catalog[1]),)

        restarted = factory((popular, "v1"))
        await restarted.load(None, "encoder", "index-2")
        restored = await restarted.restore(original.version)
        assert restored is not None
        page = await restored.recommend(query, limit=100, exclude_ids=())
        assert page.item_ids == tuple(map(str, catalog[:2]))

        for changed in (factory(), factory((popular, "v2"))):
            replacement = await changed.load(None, "encoder", "index-1")
            assert replacement.version != original.version
            assert await changed.restore(original.version) is None

    asyncio.run(check())
