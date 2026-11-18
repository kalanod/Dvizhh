from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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
            redis_url="redis://redis.invalid/0",
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
                async with databases.source.connect() as reader:
                    event = (await reader.execute(
                        text("SELECT id, title FROM events WHERE id = :id"), {"id": event_id},
                    )).one()
                    assert (event.id, event.title) == (event_id, title)

                for statement, parameters in (
                    (
                        "INSERT INTO events (id, slug, title, description, origin, format, "
                        "online_url, organizer_user_id) SELECT :new_id, :slug, title, description, "
                        "origin, format, online_url, organizer_user_id FROM events WHERE id = :id",
                        {"id": event_id, "new_id": denied_event_id, "slug": f"denied-{event_id}"},
                    ),
                    ("UPDATE events SET title = 'Forbidden' WHERE id = :id", {"id": event_id}),
                ):
                    with pytest.raises(DBAPIError) as failure:
                        async with databases.source.begin() as reader:
                            await reader.execute(text(statement), parameters)
                    assert failure.value.orig.sqlstate == "42501"

                async with databases.vector.connect() as connection:
                    await connection.execute(text("""
                        INSERT INTO event_embeddings (
                            event_id, embedding, model_name, content_hash,
                            is_candidate, source_updated_at
                        ) VALUES (:id, CAST(:vector AS vector), 'integration-test-model',
                                  'integration-test-content', true, now())
                    """), {"id": event_id, "vector": vector})
                    row = (await connection.execute(text("""
                        SELECT vector_dims(embedding) AS dimensions,
                               embedding <=> CAST(:vector AS vector) AS distance, model_name
                        FROM event_embeddings WHERE event_id = :id
                    """), {"id": event_id, "vector": vector})).one()
                    assert row.dimensions == 384
                    assert row.distance == pytest.approx(0)
                    assert row.model_name == "integration-test-model"
            assert databases.source.pool.checkedin() == databases.vector.pool.checkedin() == 0
        finally:
            try:
                await source_admin.execute(
                    "DELETE FROM events WHERE id = ANY($1::uuid[])", [event_id, denied_event_id]
                )
                await source_admin.execute("DELETE FROM profiles WHERE id = $1", profile_id)
            finally:
                await source_admin.close()

    asyncio.run(run())
