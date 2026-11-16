import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest

from dvizh_recommendation.ranking import (
    DistanceRanker,
    InvalidRankingRequest,
    NoveltyRanker,
    RelevanceRanker,
    TitleRanker,
)
from dvizh_recommendation.recommendations import RecommendationQuery

pytestmark = pytest.mark.integration

ST_PETERSBURG = (59.9386, 30.3141)
PUSHKIN = (59.7240, 30.4134)  # ~25 km
MOSCOW = (55.7558, 37.6173)  # ~630 km


class _Fixture:
    def __init__(self, connection: asyncpg.Connection) -> None:
        self.connection = connection
        self.now = datetime.now(UTC)

    async def profile(self, location: tuple[float, float] | None = None) -> UUID:
        profile_id = uuid4()
        await self.connection.execute(
            """
            INSERT INTO profiles (id, username, display_name, latitude, longitude)
            VALUES ($1, $2, 'Test user', $3, $4)
            """,
            profile_id,
            f"test-{profile_id.hex}",
            *(location or (None, None)),
        )
        return profile_id

    async def tag(self) -> UUID:
        category_id, tag_id = uuid4(), uuid4()
        await self.connection.execute(
            "INSERT INTO tag_categories (id, name, color) VALUES ($1, $2, '#123456')",
            category_id,
            f"test-{category_id.hex}",
        )
        await self.connection.execute(
            "INSERT INTO tags (id, category_id, slug, name) VALUES ($1, $2, $3, 'Test')",
            tag_id,
            category_id,
            f"test-{tag_id.hex}",
        )
        return tag_id

    async def event(
        self,
        organizer_id: UUID,
        *,
        title: str = "Test event",
        published_ago: timedelta = timedelta(hours=1),
        location: tuple[float, float] | None = None,
        tags: tuple[UUID, ...] = (),
    ) -> tuple[str, UUID]:
        event_id, occurrence_id = uuid4(), uuid4()
        location_id = None
        if location is not None:
            location_id = uuid4()
            await self.connection.execute(
                "INSERT INTO locations (id, latitude, longitude) VALUES ($1, $2, $3)",
                location_id,
                *location,
            )
        await self.connection.execute(
            """
            INSERT INTO events (
                id, slug, title, description, origin, status, visibility, format,
                online_url, location_id, organizer_user_id, published_at
            )
            VALUES ($1, $2, $3, 'Test', 'USER', 'PUBLISHED', 'PUBLIC', $4, $5, $6, $7, $8)
            """,
            event_id,
            f"test-{event_id.hex}",
            title,
            "OFFLINE" if location_id else "ONLINE",
            None if location_id else "https://example.invalid/test",
            location_id,
            organizer_id,
            self.now - published_ago,
        )
        start = self.now + timedelta(days=3)
        await self.connection.execute(
            """
            INSERT INTO event_occurrences (id, event_id, starts_at, ends_at, timezone, status)
            VALUES ($1, $2, $3, $4, 'UTC', 'SCHEDULED')
            """,
            occurrence_id,
            event_id,
            start,
            start + timedelta(hours=2),
        )
        await self.connection.executemany(
            "INSERT INTO event_tags (event_id, tag_id) VALUES ($1, $2)",
            [(event_id, tag_id) for tag_id in tags],
        )
        return str(event_id), occurrence_id

    async def going(self, user_id: UUID, occurrence_id: UUID) -> None:
        await self.connection.execute(
            """
            INSERT INTO event_participations (occurrence_id, user_id, status)
            VALUES ($1, $2, 'GOING')
            """,
            occurrence_id,
            user_id,
        )


def _run(integration_databases, scenario) -> None:
    async def check() -> None:
        connection = await asyncpg.connect(integration_databases.source_admin_url)

        class TestPool:
            @asynccontextmanager
            async def acquire(self, *, timeout):
                yield connection

        transaction = connection.transaction()
        await transaction.start()
        try:
            existing = [str(row["id"]) for row in await connection.fetch("SELECT id FROM events")]
            await scenario(_Fixture(connection), TestPool(), existing)
        finally:
            await transaction.rollback()
            await connection.close()

    asyncio.run(check())


def test_title_and_novelty_order(integration_databases):
    async def scenario(fixture, pool, existing):
        user = await fixture.profile()
        b, _ = await fixture.event(user, title="бег", published_ago=timedelta(hours=3))
        a, _ = await fixture.event(user, title="Арт", published_ago=timedelta(hours=1))
        c, _ = await fixture.event(user, title="арт", published_ago=timedelta(hours=2))
        query = RecommendationQuery(str(user), {}, {})

        by_title = await TitleRanker(pool).recommend(query, limit=10, exclude_ids=existing)
        by_novelty = await NoveltyRanker(pool).recommend(query, limit=10, exclude_ids=existing)

        assert by_title.item_ids == (a, c, b) and by_title.exhausted
        assert by_novelty.item_ids == (a, c, b)

    _run(integration_databases, scenario)


def test_distance_orders_nearest_first_and_online_last(integration_databases):
    async def scenario(fixture, pool, existing):
        user = await fixture.profile(location=ST_PETERSBURG)
        online, _ = await fixture.event(user)
        moscow, _ = await fixture.event(user, location=MOSCOW)
        pushkin, _ = await fixture.event(user, location=PUSHKIN)
        here, _ = await fixture.event(user, location=ST_PETERSBURG)
        ranker = DistanceRanker(pool)

        from_context = await ranker.recommend(
            RecommendationQuery(str(user), {"latitude": 55.75, "longitude": 37.61}, {}),
            limit=10,
            exclude_ids=existing,
        )
        from_profile = await ranker.recommend(
            RecommendationQuery(str(user), {}, {}), limit=2, exclude_ids=existing
        )

        assert from_context.item_ids == (moscow, pushkin, here, online)
        assert from_profile.item_ids == (here, pushkin) and not from_profile.exhausted

        nowhere = await fixture.profile()
        with pytest.raises(InvalidRankingRequest):
            await ranker.recommend(
                RecommendationQuery(str(nowhere), {}, {}), limit=2, exclude_ids=existing
            )

    _run(integration_databases, scenario)


def test_relevance_follows_user_interests_and_hides_dismissed(integration_databases):
    async def scenario(fixture, pool, existing):
        organizer, user = await fixture.profile(), await fixture.profile()
        music, sport = await fixture.tag(), await fixture.tag()
        _, liked_occurrence = await fixture.event(organizer, tags=(music,))
        liked = await fixture.connection.fetchval(
            "SELECT event_id FROM event_occurrences WHERE id = $1", liked_occurrence
        )
        await fixture.going(user, liked_occurrence)
        await fixture.connection.execute(
            "INSERT INTO event_favorites (user_id, event_id) VALUES ($1, $2)", user, liked
        )

        # Fresh sport event vs. an older music event the user should prefer.
        concert, _ = await fixture.event(organizer, tags=(music,), published_ago=timedelta(days=10))
        match, _ = await fixture.event(organizer, tags=(sport,), published_ago=timedelta(0))
        dismissed, _ = await fixture.event(organizer, tags=(music,))
        await fixture.connection.execute(
            "INSERT INTO event_dismissals (user_id, event_id) VALUES ($1, $2)",
            user,
            UUID(dismissed),
        )
        ranker = RelevanceRanker(pool)
        excluded = [*existing, str(liked)]

        personal = await ranker.recommend(
            RecommendationQuery(str(user), {}, {}), limit=10, exclude_ids=excluded
        )
        cold_start = await ranker.recommend(
            RecommendationQuery(str(uuid4()), {}, {}), limit=10, exclude_ids=excluded
        )

        assert personal.item_ids[:2] == (concert, match)
        assert dismissed not in personal.item_ids
        # Without history: freshness wins and nothing is hidden.
        assert cold_start.item_ids[0] == match
        assert dismissed in cold_start.item_ids

    _run(integration_databases, scenario)
