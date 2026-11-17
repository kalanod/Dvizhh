import asyncio

import pytest

from dvizh_recommendation.candidates import LatestRecommendations, get_candidates
from dvizh_recommendation.recommendations import RecommendationQuery


@pytest.mark.parametrize(
    ("limit", "error"),
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)],
)
def test_get_candidates_rejects_invalid_limit(limit, error):
    async def check():
        with pytest.raises(error):
            await get_candidates(None, limit=limit)

    asyncio.run(check())


def test_latest_recommendations_reject_unsupported_filters():
    async def check():
        provider = LatestRecommendations(None)
        query = RecommendationQuery(user_id="user", context={}, filters={"city": "Moscow"})
        with pytest.raises(NotImplementedError):
            await provider.recommend(query, limit=100, exclude_ids=())

    asyncio.run(check())
