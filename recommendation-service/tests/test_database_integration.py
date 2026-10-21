from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

import asyncpg
import pytest

from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import connect_databases

if TYPE_CHECKING:
    from conftest import IntegrationDatabases


pytestmark = pytest.mark.integration


def test_source_reader_and_vector_writer_work_with_real_schemas(
    integration_databases: IntegrationDatabases,
) -> None:
    async def run() -> None:
        settings = Settings(
            source_database_url=integration_databases.source_url,
            vector_database_url=integration_databases.vector_url,
            database_timeout_seconds=2,
            _env_file=None,
        )
        profile_id = uuid4()
        event_id = uuid4()
        denied_event_id = uuid4()
        title = "Recommendation database integration test"
        vector = "[1," + ",".join("0" for _ in range(383)) + "]"
        source_admin = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            async with source_admin.transaction():
                await source_admin.execute(
                    "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, $3)",
                    profile_id,
                    f"recsys-test-{profile_id.hex}",
                    "Recommendation test organizer",
                )
                await source_admin.execute(
                    """
                    INSERT INTO events (
                        id, slug, title, description, origin, status,
                        format, online_url, organizer_user_id
                    ) VALUES ($1, $2, $3, $4, 'USER', 'PUBLISHED', 'ONLINE', $5, $6)
                    """,
                    event_id,
                    f"recsys-test-{event_id.hex}",
                    title,
                    title,
                    "https://example.invalid/integration-test",
                    profile_id,
                )
            async with connect_databases(settings) as databases:
                event = await databases.source.fetchrow(
                    "SELECT id, title FROM events WHERE id = $1", event_id
                )
                assert event is not None
                assert event["id"] == event_id
                assert event["title"] == title
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await databases.source.execute(
                        """
                        INSERT INTO events (
                            id, slug, title, description, origin, format,
                            online_url, organizer_user_id
                        ) SELECT $1, $2, title, description, origin, format,
                                 online_url, organizer_user_id
                          FROM events WHERE id = $3
                        """,
                        denied_event_id,
                        f"recsys-denied-{denied_event_id.hex}",
                        event_id,
                    )
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await databases.source.execute(
                        "UPDATE events SET title = $2 WHERE id = $1", event_id, "Forbidden update"
                    )

                async with databases.vector.acquire() as connection:
                    transaction = connection.transaction()
                    await transaction.start()
                    try:
                        await connection.execute(
                            """
                            INSERT INTO event_embeddings (
                                event_id, embedding, model_name, content_hash,
                                is_candidate, source_updated_at
                            ) VALUES ($1, $2::vector, $3, $4, true, now())
                            """,
                            event_id,
                            vector,
                            "integration-test-model",
                            "integration-test-content",
                        )
                        row = await connection.fetchrow(
                            """
                            SELECT vector_dims(embedding) AS dimensions,
                                   embedding <=> $2::vector AS distance,
                                   model_name
                            FROM event_embeddings WHERE event_id = $1
                            """,
                            event_id,
                            vector,
                        )
                        assert row is not None
                        assert row["dimensions"] == 384
                        assert row["distance"] == pytest.approx(0)
                        assert row["model_name"] == "integration-test-model"
                    finally:
                        await transaction.rollback()
            assert databases.source.get_size() == 0
            assert databases.vector.get_size() == 0
        finally:
            try:
                await source_admin.execute(
                    "DELETE FROM events WHERE id = ANY($1::uuid[])", [event_id, denied_event_id]
                )
                await source_admin.execute("DELETE FROM profiles WHERE id = $1", profile_id)
            finally:
                await source_admin.close()

    asyncio.run(run())
