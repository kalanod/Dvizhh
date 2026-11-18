from __future__ import annotations

import asyncio
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import asyncpg
import grpc
import pytest
from redis.asyncio import Redis

from dvizh_recommendation.config import Settings
from dvizh_recommendation.embedding_encoder import load_encoder
from dvizh_recommendation.embedding_snapshot import EmbeddingSnapshot
from dvizh_recommendation.encoder_data import _export, read_snapshot_inputs
from dvizh_recommendation.generate_embeddings import build_snapshot, write_snapshot
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated.recommendation_service_pb2_grpc import (
    RecommendationServiceStub,
)
from dvizh_recommendation.index_revision import hnsw_index_name
from dvizh_recommendation.main import running_server
from dvizh_recommendation.pagination import SessionStore
from dvizh_recommendation.vector_index import refresh_index

if TYPE_CHECKING:
    from conftest import IntegrationDatabases

pytestmark = pytest.mark.integration


def test_confirmed_history_trains_and_serves_two_tower_through_hnsw(
    integration_databases: IntegrationDatabases,
    integration_redis_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = os.environ.get("TEST_MLFLOW_TRACKING_URI")
    if not registry:
        pytest.skip("Set TEST_MLFLOW_TRACKING_URI to an isolated MLflow server")
    pytest.importorskip("torch", reason="Install the encoder dependency group")
    pytest.importorskip("safetensors", reason="Install the encoder dependency group")
    import mlflow

    from dvizh_recommendation.encoder_training import train_and_register_encoder

    monkeypatch.setenv("MLFLOW_TRACKING_URI", registry)
    monkeypatch.setenv("SOURCE_DATABASE_URL", integration_databases.source_url)
    client = mlflow.MlflowClient(tracking_uri=registry)
    now = datetime.now(UTC)
    history_start = now - timedelta(days=30)
    validation_start = now - timedelta(days=16)
    marker = f"tower{uuid4().hex}"
    organizer = uuid4()
    topics = ("керамика глина гончарный мастерская", "хоккей шайба коньки лед стадион")
    viewers = {topic: uuid4() for topic in topics}
    future = {topic: uuid4() for topic in topics}
    histories = {topic: [uuid4() for _ in range(6)] for topic in topics}
    event_ids = [*future.values(), *(item for past in histories.values() for item in past)]
    occurrences = {item_id: uuid4() for item_id in event_ids}
    sessions = {topic: str(uuid4()) for topic in topics}

    async def seed(source: asyncpg.Connection) -> None:
        async with source.transaction():
            await source.executemany(
                "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, 'Encoder')",
                [(user, f"tower-{user.hex}") for user in (organizer, *viewers.values())],
            )
            for topic in topics:
                title = f"{marker} {topic}"
                await source.executemany(
                    """
                    INSERT INTO events (
                        id, slug, title, description, origin, status, visibility, format,
                        online_url, organizer_user_id, published_at
                    ) VALUES ($1, $2, $3::text, $3::text, 'USER', $4, 'PUBLIC', 'ONLINE',
                              'https://example.invalid/tower', $5, $6)
                    """,
                    [
                        (item, f"tower-{item}", title, status, organizer, history_start)
                        for item, status in (
                            *((item, "COMPLETED") for item in histories[topic]),
                            (future[topic], "PUBLISHED"),
                        )
                    ],
                )
                for offset, item in enumerate(histories[topic]):
                    confirmed_at = now - timedelta(days=20 - offset)
                    await source.execute(
                        """
                        INSERT INTO event_occurrences (id, event_id, starts_at, timezone)
                        VALUES ($1, $2, $3, 'UTC')
                        """,
                        occurrences[item], item, confirmed_at + timedelta(hours=3),
                    )
                    participation = await source.fetchval(
                        """
                        INSERT INTO event_participations (occurrence_id, user_id, status)
                        VALUES ($1, $2, 'GOING') RETURNING id
                        """,
                        occurrences[item], viewers[topic],
                    )
                    await source.execute(
                        """
                        INSERT INTO participation_status_history (
                            participation_id, to_status, changed_at
                        ) VALUES ($1, 'GOING', $2)
                        """,
                        participation, confirmed_at,
                    )
                await source.execute(
                    """
                    INSERT INTO event_occurrences (id, event_id, starts_at, timezone, status)
                    VALUES ($1, $2, $3, 'UTC', 'SCHEDULED')
                    """,
                    occurrences[future[topic]], future[topic], now + timedelta(days=2),
                )

    async def serve(uri: str, revision: str) -> None:
        settings = Settings(
            grpc_bind_address="127.0.0.1:0",
            source_database_url=integration_databases.source_url,
            vector_database_url=integration_databases.vector_url,
            redis_url=integration_redis_url,
            vector_model_id=uri,
            vector_index_revision=revision,
            _env_file=None,
        )
        async with (
            running_server(settings) as (_, port),
            grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
        ):
            service = RecommendationServiceStub(channel)
            for topic in topics:
                request = pb.GetRecommendationsRequest(
                    user_id=str(viewers[topic]), session_id=sessions[topic],
                    request_id=str(uuid4()),
                    page_size=2,
                )
                request.filters["q"].string_value = marker
                response = await service.GetRecommendations(request, timeout=5)
                assert [UUID(item.item_id) for item in response.items] == [
                    future[topic], *(item for other, item in future.items() if other != topic),
                ]
                assert UUID(response.items[0].occurrence_id) == occurrences[future[topic]]

    async def run() -> None:
        async with (
            asyncpg.create_pool(
                integration_databases.source_admin_url, min_size=1, max_size=1
            ) as catalogue,
            asyncpg.create_pool(
                integration_databases.vector_url, min_size=1, max_size=1,
            ) as vector_db,
            catalogue.acquire() as source,
            integration_databases.connections() as (source_readonly, index),
            vector_db.acquire() as writer,
            Redis.from_url(integration_redis_url) as redis,
        ):
            revision = None
            try:
                await seed(source)
                data = tmp_path / "encoder-dataset.json"
                dataset_version = await _export(data, history_start, now)
                uri = await asyncio.to_thread(
                    train_and_register_encoder,
                    data,
                    validation_start=validation_start,
                    experiment=marker,
                    name=marker,
                    git_sha="fixture",
                )
                version = client.get_model_version(marker, uri.rsplit("/", 1)[-1])
                assert version.tags["dataset_version"] == dataset_version
                encoder = await asyncio.to_thread(load_encoder, uri)
                items, users = await read_snapshot_inputs(source_readonly, history_start, now)
                snapshot = build_snapshot(encoder, items, users, generated_at=now)
                output = tmp_path / "embeddings.json"
                write_snapshot(snapshot, output)
                loaded = EmbeddingSnapshot.model_validate_json(output.read_bytes())
                published = await refresh_index(source_readonly, index, loaded)
                revision = str(published["revision"])

                with socket.socket() as unavailable, monkeypatch.context() as offline:
                    unavailable.bind(("127.0.0.1", 0))
                    offline.setenv(
                        "MLFLOW_TRACKING_URI", f"http://127.0.0.1:{unavailable.getsockname()[1]}"
                    )
                    await serve(uri, revision)
            finally:
                await source.execute("DELETE FROM events WHERE id = ANY($1::uuid[])", event_ids)
                await source.execute(
                    "DELETE FROM profiles WHERE id = ANY($1::uuid[])",
                    [organizer, *viewers.values()],
                )
                await writer.execute(
                    "DELETE FROM recommendation_pages WHERE session_id = ANY($1::text[])",
                    list(sessions.values()),
                )
                if revision is not None:
                    await writer.execute(f"DROP INDEX public.{hnsw_index_name(revision)}")
                    tables = ("user_embeddings", "event_embeddings", "embedding_index_versions")
                    for table in tables:
                        await writer.execute(
                            f"DELETE FROM public.{table} WHERE model_name = $1", revision,
                        )
                await redis.delete(*(SessionStore.key(session) for session in sessions.values()))

    try:
        asyncio.run(run())
    finally:
        if client.search_registered_models(filter_string=f"name = '{marker}'"):
            client.delete_registered_model(marker)
        if experiment := client.get_experiment_by_name(marker):
            client.delete_experiment(experiment.experiment_id)
