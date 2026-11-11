import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

from dvizh_recommendation.candidates import LatestRecommendations, get_candidates
from dvizh_recommendation.catalog import filter_available_items
from dvizh_recommendation.recommendations import RecommendationQuery

pytestmark = pytest.mark.integration


def test_latest_recommendations_filter_and_paginate(integration_databases):
    async def check():
        connection = await asyncpg.connect(integration_databases.source_admin_url)

        class TestPool:
            @asynccontextmanager
            async def acquire(self, *, timeout):
                yield connection

        now = datetime.now(UTC)
        future = now + timedelta(days=5)
        past = now - timedelta(days=5)

        profile_id = uuid4()

        cases = [
            ("valid", "PUBLISHED", "PUBLIC", False, future, "SCHEDULED"),
            ("private", "PUBLISHED", "PRIVATE", False, future, "SCHEDULED"),
            ("draft", "DRAFT", "PUBLIC", False, future, "SCHEDULED"),
            ("deleted", "PUBLISHED", "PUBLIC", True, future, "SCHEDULED"),
            ("past", "PUBLISHED", "PUBLIC", False, past, "SCHEDULED"),
            ("cancelled", "PUBLISHED", "PUBLIC", False, future, "CANCELLED"),
        ]

        ids = {}

        transaction = connection.transaction()
        transaction_started = False

        try:
            await transaction.start()
            transaction_started = True

            await connection.execute(
                """
                INSERT INTO profiles (id, username, display_name)
                VALUES ($1, $2, $3)
                """,
                profile_id,
                f"test-{profile_id.hex}",
                "Test organizer",
            )

            for name, status, visibility, deleted, start, occ_status in cases:
                event_id = uuid4()
                ids[name] = event_id

                await connection.execute(
                    """
                    INSERT INTO events (
                        id, slug, title, description,
                        origin, status, visibility,
                        format, online_url,
                        organizer_user_id,
                        published_at, deleted_at
                    )
                    VALUES (
                        $1, $2, $3, $4,
                        'USER', $5, $6,
                        'ONLINE', $7,
                        $8, $9, $10
                    )
                    """,
                    event_id,
                    f"test-{event_id.hex}",
                    f"Test {name}",
                    f"Description for {name}",
                    status,
                    visibility,
                    "https://example.invalid/test",
                    profile_id,
                    now,
                    now if deleted else None,
                )

                await connection.execute(
                    """
                    INSERT INTO event_occurrences (
                        id, event_id, starts_at,
                        ends_at, timezone, status
                    )
                    VALUES ($1, $2, $3, $4, 'UTC', $5)
                    """,
                    uuid4(),
                    event_id,
                    start,
                    start + timedelta(hours=2),
                    occ_status,
                )

            await connection.execute(
                """
                INSERT INTO event_occurrences (
                    id, event_id, starts_at,
                    ends_at, timezone, status
                )
                VALUES ($1, $2, $3, $4, 'UTC', 'SCHEDULED')
                """,
                uuid4(),
                ids["valid"],
                future + timedelta(days=1),
                future + timedelta(days=1, hours=2),
            )

            result = await get_candidates(
                TestPool(),
                limit=10000,
            )

            result_ids = set(result)

            assert ids["valid"] in result_ids

            for name in (
                "private",
                "draft",
                "deleted",
                "past",
                "cancelled",
            ):
                assert ids[name] not in result_ids, f"Event {name} should not be returned"

            assert result.count(ids["valid"]) == 1

            without_valid = await get_candidates(
                TestPool(), limit=10000, exclude_ids=[ids["valid"]]
            )
            assert ids["valid"] not in without_valid

            existing_ids = [
                str(row["id"]) for row in await connection.fetch("SELECT id FROM events")
            ]
            item_ids = [uuid4() for _ in range(101)]
            await connection.executemany(
                """
                INSERT INTO events (
                    id, slug, title, description, origin, status, visibility,
                    format, online_url, organizer_user_id, published_at
                )
                VALUES (
                    $1, $2, 'Test event', 'Test description', 'USER', 'PUBLISHED',
                    'PUBLIC', 'ONLINE', 'https://example.invalid/test', $3, $4
                )
                """,
                [
                    (item_id, f"test-{item_id.hex}", profile_id, now - timedelta(seconds=i))
                    for i, item_id in enumerate(item_ids)
                ],
            )
            await connection.executemany(
                """
                INSERT INTO event_occurrences (id, event_id, starts_at, ends_at, timezone, status)
                VALUES ($1, $2, $3, $4, 'UTC', 'SCHEDULED')
                """,
                [(uuid4(), item_id, future, future + timedelta(hours=2)) for item_id in item_ids],
            )
            provider = LatestRecommendations(TestPool())
            query = RecommendationQuery(user_id=str(profile_id), context={}, filters={})
            expected = tuple(str(item_id) for item_id in item_ids)

            page_ids = [
                expected[42],
                *(str(item_id) for item_id in ids.values()),
                str(uuid4()),
                expected[5],
            ]
            available = await filter_available_items(TestPool(), page_ids)
            assert available == (expected[42], str(ids["valid"]), expected[5])

            first = await provider.recommend(query, limit=100, exclude_ids=existing_ids)
            assert first.item_ids == expected[:100]
            assert not first.exhausted

            last = await provider.recommend(
                query, limit=100, exclude_ids=[*existing_ids, *first.item_ids]
            )
            assert last.item_ids == expected[100:]
            assert last.exhausted

            exact = await provider.recommend(
                query, limit=100, exclude_ids=[*existing_ids, expected[0]]
            )
            assert exact.item_ids == expected[1:]
            assert exact.exhausted

        finally:
            try:
                if transaction_started:
                    await transaction.rollback()
            finally:
                await connection.close()

    asyncio.run(check())
