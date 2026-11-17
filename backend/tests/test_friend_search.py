import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_event_sorting import Catalog, run_in_rollback

from dvizh_backend.api.dependencies import get_user_service
from dvizh_backend.api.routers.friends import router
from dvizh_backend.database.models import Friendship, Profile
from dvizh_backend.services.user_service import UserService


def test_friend_search_route_passes_bounded_pages_and_query_to_service():
    app = FastAPI()
    app.include_router(router)
    service = SimpleNamespace(search_friends=AsyncMock(return_value=[]))
    app.dependency_overrides[get_user_service] = lambda: service
    user_id = uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/users/{user_id}/friends/search", params={
            "q": "Имя", "offset": 20, "limit": 20,
        })
        assert response.status_code == 200
        service.search_friends.assert_awaited_once_with(user_id, "Имя", offset=20, limit=20)
        for params in ({"limit": 101}, {"offset": -1}, {"q": "x" * 121}):
            response = client.get(f"/api/users/{user_id}/friends/search", params=params)
            assert response.status_code == 422


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_friend_search_only_returns_active_accepted_friends_with_stable_pages():
    async def scenario(catalog: Catalog, _queries):
        owner = await catalog.profile()
        expected = []
        for index in range(25):
            other = await catalog.profile()
            profile = await catalog.session.get(Profile, other)
            profile.display_name = f"Друг {index:02d}"
            if index == 24:
                profile.status = "SUSPENDED"
            low, high = sorted([owner, other], key=lambda item: item.int)
            catalog.session.add(Friendship(
                user_low_id=low, user_high_id=high, requested_by_user_id=owner,
                status="PENDING" if index == 23 else "ACCEPTED", requested_at=catalog.now,
                responded_at=None if index == 23 else catalog.now,
            ))
            if index < 23:
                expected.append(other)
        await catalog.profile()  # An unrelated active user is not a search result.
        await catalog.session.flush()
        service = UserService(catalog.session)
        first = await service.search_friends(owner, "", limit=20)
        second = await service.search_friends(owner, "", offset=20, limit=20)
        assert [profile.id for profile in first + second] == expected
        assert len(first) == 20 and len(second) == 3
        assert len(await service.search_friends(owner, " ДРУГ 0 ")) == 10
        assert await service.search_friends(owner, "%") == []
        assert await service.search_friends(owner, "_")  # Literal underscores in usernames.
        assert [profile.id for profile in await service.search_friends(
            owner, first[0].username.upper(),
        )] == [first[0].id]

    run_in_rollback(scenario)
