# имитирует PostgreSQL и проверяет, что функция возвращает список ID событий. 
# Второй проверяет, что нельзя запросить нулевое количество мероприятий.

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from dvizh_recommendation.candidates import get_candidates


def test_get_candidates_returns_ids():
    event_id_1 = uuid4()
    event_id_2 = uuid4()

    class FakeConnection:
        async def fetch(self, query, limit):
            assert "EXISTS" in query
            assert limit == 20
            return [
                {"id": event_id_1},
                {"id": event_id_2},
            ]

    class FakePool:
        @asynccontextmanager
        async def acquire(self):
            yield FakeConnection()

    result = asyncio.run(get_candidates(FakePool()))

    assert result == [event_id_1, event_id_2]


def test_get_candidates_rejects_invalid_limit():
    async def check():
        with pytest.raises(ValueError):
            await get_candidates(None, limit=0)

    asyncio.run(check())