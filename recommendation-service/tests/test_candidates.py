import asyncio

import pytest

from dvizh_recommendation.candidates import LatestRecommendations
from dvizh_recommendation.recommendations import RecommendationQuery


def test_latest_recommendations_reject_unsupported_filters():
    async def check():
        provider = LatestRecommendations(None)
        query = RecommendationQuery(user_id="user", context={}, filters={"city": "Moscow"})
        with pytest.raises(NotImplementedError):
            await provider.recommend(query, limit=100, exclude_ids=())

    asyncio.run(check())
