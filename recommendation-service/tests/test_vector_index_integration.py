from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import asyncpg
import grpc
import pytest
from redis.asyncio import Redis

from dvizh_recommendation.config import Settings
from dvizh_recommendation.embedding_snapshot import (
    EmbeddingSnapshot,
    ItemVector,
    UserVector,
    catalog_content_hash,
)
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated.recommendation_service_pb2_grpc import (
    RecommendationServiceStub,
)
from dvizh_recommendation.main import running_server
from dvizh_recommendation.pagination import SessionStore
from dvizh_recommendation.retrieval import EmbeddingSpace
from dvizh_recommendation.vector_index import refresh_index

if TYPE_CHECKING:
    from conftest import IntegrationDatabases

pytestmark = pytest.mark.integration


def test_sessions_keep_their_index_across_republication_and_restart(
    integration_databases: IntegrationDatabases,
    integration_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dvizh_recommendation.pagination.BATCH_SIZE", 1)
    known_viewer, new_viewer = uuid4(), uuid4()
    distractor, first, second, third = uuid4(), uuid4(), uuid4(), uuid4()
    items = (distractor, first, second, third)
    original, cold, no_matches, pinned_session, fresh_session, filtered_session = (
        str(uuid4()) for _ in range(6)
    )
    sessions = (original, cold, no_matches, pinned_session, fresh_session, filtered_session)
    marker = f"vector{uuid4().hex}"
    model_id = f"fixture-{uuid4()}"
    now = datetime.now(UTC)
    selected_date = (now + timedelta(days=2)).date().isoformat()
    nearest = (1.0, 0.0) + (0.0,) * 382
    close = (0.8, 0.6) + (0.0,) * 382
    medium = (0.6, 0.8) + (0.0,) * 382
    distant = (0.0, 1.0) + (0.0,) * 382
    content_hash = catalog_content_hash(marker, marker, ())

    def snapshot(
        generated_at: datetime,
        scores: tuple[tuple[float, ...], ...],
        viewers: tuple[UUID, ...],
    ) -> EmbeddingSnapshot:
        return EmbeddingSnapshot(
            space=EmbeddingSpace(model_id=model_id, dimension=384, metric="cosine"),
            generated_at=generated_at,
            users=tuple(UserVector(user_id=viewer, values=nearest) for viewer in viewers),
            items=tuple(
                ItemVector(item_id=item, content_hash=content_hash, values=values)
                for item, values in zip(items, scores, strict=True)
            ),
        )

    @asynccontextmanager
    async def server(
        revision: str | None = None, previous_revision: str | None = None,
    ) -> AsyncIterator[RecommendationServiceStub]:
        settings = Settings(
            grpc_bind_address="127.0.0.1:0",
            source_database_url=integration_databases.source_url,
            vector_database_url=integration_databases.vector_url,
            redis_url=integration_redis_url,
            vector_model_id=model_id,
            vector_index_revision=revision,
            previous_vector_model_id=model_id if previous_revision else None,
            previous_vector_index_revision=previous_revision,
            _env_file=None,
        )
        async with (
            running_server(settings) as (_, port),
            grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
        ):
            yield RecommendationServiceStub(channel)

    def request_for_page(
        viewer: UUID,
        session: str,
        token: str | None = None,
    ) -> pb.GetRecommendationsRequest:
        request = pb.GetRecommendationsRequest(
            user_id=str(viewer), session_id=session, request_id=str(uuid4()), page_size=1
        )
        request.filters["q"].string_value = marker
        request.filters["date_from"].string_value = selected_date
        request.filters["date_to"].string_value = selected_date
        if token is not None:
            request.page_token = token
        return request

    async def page(
        client: RecommendationServiceStub,
        viewer: UUID,
        session: str,
        expected_item: UUID,
        token: str | None = None,
    ) -> pb.GetRecommendationsResponse:
        request = request_for_page(viewer, session, token)
        response = await client.GetRecommendations(request, timeout=5)
        assert [candidate.item_id for candidate in response.items] == [str(expected_item)]
        return response

    async def run() -> None:
        async with (
            asyncpg.create_pool(
                integration_databases.source_admin_url, min_size=1, max_size=1
            ) as source,
            asyncpg.create_pool(
                integration_databases.vector_url, min_size=1, max_size=1
            ) as vectors,
            source.acquire() as catalog,
            vectors.acquire() as writer,
            integration_databases.connections() as (source, index),
            Redis.from_url(integration_redis_url) as redis,
        ):
            try:
                await catalog.executemany(
                    "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, 'Viewer')",
                    [(viewer, f"vector-{viewer.hex}") for viewer in (known_viewer, new_viewer)],
                )
                await catalog.executemany(
                    """
                    INSERT INTO events (
                        id, slug, title, description, origin, status, visibility, format,
                        online_url, organizer_user_id, published_at
                    ) VALUES ($1, $2, $3::text, $3::text, 'USER', 'PUBLISHED', 'PUBLIC', 'ONLINE',
                              'https://example.invalid/vector', $4, $5)
                    """,
                    [
                        (item, f"vector-{item}", marker, known_viewer, now - timedelta(days=offset))
                        for offset, item in enumerate(items)
                    ],
                )
                occurrences = {item: uuid4() for item in items}
                await catalog.executemany(
                    """
                    INSERT INTO event_occurrences (id, event_id, starts_at, timezone, status)
                    VALUES ($1, $2, $3, 'UTC', 'SCHEDULED')
                    """,
                    [
                        (
                            occurrences[item], item,
                            now + timedelta(days=1 if item == distractor else 2),
                        )
                        for item in items
                    ],
                )

                initial = snapshot(now, (nearest, distant, close, medium), (known_viewer,))
                initial_revision = (await refresh_index(source, index, initial))["revision"]
                async with server() as client:
                    by_index = await page(client, known_viewer, original, second)
                    assert UUID(by_index.items[0].occurrence_id) == occurrences[second]
                    assert by_index.HasField("next_page_token")
                    logged_score = await writer.fetchval(
                        "SELECT (items->0->'features'->>'hnsw_score')::float8 "
                        "FROM public.recommendation_pages WHERE session_id = $1", original,
                    )
                    assert logged_score == pytest.approx(0.8)
                    with pytest.raises(grpc.aio.AioRpcError) as error:
                        await client.GetRecommendations(
                            request_for_page(new_viewer, cold), timeout=5
                        )
                    assert error.value.code() == grpc.StatusCode.FAILED_PRECONDITION
                    assert error.value.trailing_metadata().get("recsys-reason") == "no-user-vector"

                    empty_request = request_for_page(new_viewer, no_matches)
                    empty_request.filters["q"].string_value = f"missing-{marker}"
                    empty = await client.GetRecommendations(empty_request, timeout=5)
                    assert not empty.items and not empty.HasField("next_page_token")

                updated = snapshot(
                    now + timedelta(seconds=1),
                    (nearest, close, distant, medium),
                    (known_viewer, new_viewer),
                )
                updated_revision = (await refresh_index(source, index, updated))["revision"]
                assert updated_revision != initial_revision
                assert isinstance(initial_revision, str) and isinstance(updated_revision, str)
                with pytest.raises(ValueError, match="newer or different snapshot"):
                    await refresh_index(source, index, initial)

                stale_item = updated.items[0].model_copy(update={
                    "content_hash": catalog_content_hash("old title", marker, ()),
                })
                stale = updated.model_copy(update={
                    "generated_at": now + timedelta(seconds=2), "items": (stale_item,),
                })
                with pytest.raises(ValueError, match="no active items matching the catalogue"):
                    await refresh_index(source, index, stale)

                async with server(initial_revision) as client:
                    await page(client, known_viewer, pinned_session, second)

                async with server(updated_revision, initial_revision) as client:
                    await page(client, known_viewer, original, third, by_index.next_page_token)
                    fresh = await page(client, new_viewer, fresh_session, first)
                    assert fresh.HasField("next_page_token")
                    await page(client, new_viewer, fresh_session, third, fresh.next_page_token)

                    await catalog.execute(
                        "UPDATE events SET visibility = 'PRIVATE' WHERE id = $1", third
                    )
                    filtered = await page(client, new_viewer, filtered_session, first)
                    assert filtered.HasField("next_page_token")
                    last = await page(
                        client, new_viewer, filtered_session, second, filtered.next_page_token
                    )
                    assert not last.HasField("next_page_token")
            finally:
                await catalog.execute("DELETE FROM events WHERE id = ANY($1::uuid[])", list(items))
                await catalog.execute(
                    "DELETE FROM profiles WHERE id = ANY($1::uuid[])", [known_viewer, new_viewer]
                )
                await writer.execute(
                    "DELETE FROM public.recommendation_pages WHERE session_id = ANY($1::text[])",
                    sessions,
                )
                revisions = [
                    row["model_name"]
                    for row in await writer.fetch(
                        "SELECT model_name FROM public.embedding_index_versions "
                        "WHERE model_id = $1",
                        model_id,
                    )
                ]
                for table in ("user_embeddings", "event_embeddings", "embedding_index_versions"):
                    await writer.execute(
                        f"DELETE FROM public.{table} WHERE model_name = ANY($1::text[])", revisions
                    )
                for revision in revisions:
                    index = await writer.fetchval(
                        """
                        SELECT quote_ident(indexname) FROM pg_indexes
                        WHERE schemaname = 'public' AND tablename = 'event_embeddings'
                          AND indexdef LIKE $1
                        """,
                        f"%'{revision}'%",
                    )
                    if index is not None:
                        await writer.execute(f"DROP INDEX public.{index}")
                await redis.delete(*(SessionStore.key(session) for session in sessions))

    asyncio.run(run())
