from __future__ import annotations

import asyncio
import hashlib
import json
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
from dvizh_recommendation.model_registry import load_ranker
from dvizh_recommendation.pagination import SessionStore
from dvizh_recommendation.prepare_model import prepare_ranker
from dvizh_recommendation.retrieval import EmbeddingSpace
from dvizh_recommendation.train import train_and_register
from dvizh_recommendation.vector_index import refresh_index

if TYPE_CHECKING:
    from conftest import IntegrationDatabases

pytestmark = pytest.mark.integration


def write_learning_fixture(
    directory: Path, feature_version: str, samples: list[tuple[dict[str, float | None], int]],
) -> str:
    directory.mkdir()
    example = {
        "hours_until_start": 0,
        "hours_since_publication": 0,
        "participants_count": 0,
        "price_type": "FREE",
        "format": "ONLINE",
        "join_policy": "OPEN",
    }
    examples = b"".join(
        json.dumps(
            {
                "split": split,
                "features": {**example, **features},
                "label": label,
            }
        ).encode()
        + b"\n"
        for split in ("train", "validation", "test")
        for features, label in samples
    )
    manifest = {
        "schema_version": 1,
        "feature_version": feature_version,
        "examples_sha256": hashlib.sha256(examples).hexdigest(),
    }
    version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    (directory / "examples.jsonl").write_bytes(examples)
    (directory / "manifest.json").write_text(json.dumps({**manifest, "dataset_version": version}))
    return version


def test_prepared_model_version_controls_the_live_order_without_mlflow(
    integration_databases: IntegrationDatabases,
    integration_redis_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = os.environ.get("TEST_MLFLOW_TRACKING_URI")
    if not registry:
        pytest.skip("Set TEST_MLFLOW_TRACKING_URI to an isolated MLflow server")
    pytest.importorskip("sklearn", reason="Install the train dependency group")
    import mlflow

    monkeypatch.setenv("MLFLOW_TRACKING_URI", registry)
    profile = uuid4()
    new_event, popular_event, unindexed_event = uuid4(), uuid4(), uuid4()
    marker = f"model{profile.hex}"
    experiment = f"pipeline-{profile}"
    vector_version = f"vectors-{profile}"
    prepared_directory = tmp_path / "prepared"
    version = write_learning_fixture(
        tmp_path / "catalog", "catalog-v1",
        [({"participants_count": 0}, 1), ({"participants_count": 1}, 0)],
    )
    write_learning_fixture(
        tmp_path / "scored", "catalog-hnsw-v1",
        [({"hnsw_score": None}, 0), ({"hnsw_score": 0.0}, 1), ({"hnsw_score": 1.0}, 0)],
    )
    client = mlflow.MlflowClient(tracking_uri=registry)

    async def serve(first_uri: str, second_uri: str) -> None:
        source = await asyncpg.connect(integration_databases.source_admin_url)
        journal = await asyncpg.connect(integration_databases.vector_url)
        session_ids = [str(uuid4()), str(uuid4())]
        revision = None
        try:
            async with source.transaction():
                await source.execute(
                    "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, $2)",
                    profile,
                    marker,
                )
                now = datetime.now(UTC)
                for event_id, publication in (
                    (new_event, now),
                    (popular_event, now - timedelta(days=1)),
                    (unindexed_event, now),
                ):
                    await source.execute(
                        """
                        INSERT INTO events (
                            id, slug, title, description, origin, status, visibility, format,
                            online_url, organizer_user_id, published_at
                        ) VALUES ($1, $2, $3::text, $3::text, 'USER', 'PUBLISHED', 'PUBLIC',
                                  'ONLINE', 'https://example.invalid/model', $4, $5)
                        """,
                        event_id,
                        f"model-{event_id}",
                        marker,
                        profile,
                        publication,
                    )
                    occurrence = await source.fetchval(
                        """
                        INSERT INTO event_occurrences (event_id, starts_at, timezone, status)
                        VALUES ($1, $2, 'UTC', 'SCHEDULED') RETURNING id
                        """,
                        event_id,
                        now + timedelta(days=5),
                    )
                    if event_id == popular_event:
                        await source.execute(
                            """
                            INSERT INTO event_participations (occurrence_id, user_id, status)
                            VALUES ($1, $2, 'GOING')
                            """,
                            occurrence,
                            profile,
                        )

            nearest = (1.0, 0.0) + (0.0,) * 382
            distant = (0.0, 1.0) + (0.0,) * 382
            content_hash = catalog_content_hash(marker, marker, ())
            snapshot = EmbeddingSnapshot(
                space=EmbeddingSpace(model_id=vector_version, dimension=384, metric="cosine"),
                generated_at=now,
                users=(UserVector(user_id=profile, values=nearest),),
                items=(
                    ItemVector(item_id=new_event, content_hash=content_hash, values=nearest),
                    ItemVector(item_id=popular_event, content_hash=content_hash, values=distant),
                ),
            )
            async with integration_databases.connections() as (catalog, vectors):
                revision = (await refresh_index(catalog, vectors, snapshot))["revision"]

            for uri, session_id, expected in (
                (first_uri, session_ids[0], [new_event, popular_event]),
                (second_uri, session_ids[1], [popular_event, new_event]),
            ):
                settings = Settings(
                    grpc_bind_address="127.0.0.1:0",
                    source_database_url=integration_databases.source_url,
                    vector_database_url=integration_databases.vector_url,
                    redis_url=integration_redis_url,
                    ranker_model_uri=uri,
                    ranker_model_dir=prepared_directory,
                    vector_model_id=vector_version,
                    _env_file=None,
                )
                async with (
                    running_server(settings) as (_, port),
                    grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
                ):
                    request = pb.GetRecommendationsRequest(
                        user_id=str(profile), session_id=session_id, request_id=str(uuid4())
                    )
                    request.filters["q"].string_value = marker
                    response = await RecommendationServiceStub(channel).GetRecommendations(
                        request, timeout=5
                    )
                    assert [UUID(item.item_id) for item in response.items] == expected
                    if uri == second_uri:
                        page = await journal.fetchval(
                            "SELECT items FROM recommendation_pages WHERE request_id = $1",
                            request.request_id,
                        )
                        features = json.loads(page)[0]["features"]
                        assert features["hnsw_score"] == pytest.approx(0)
                        ranker = await load_ranker(uri, prepared_directory)
                        observed, missing = await ranker.score(
                            [features, {**features, "hnsw_score": None}]
                        )
                        assert observed > missing
        finally:
            await source.execute(
                "DELETE FROM events WHERE id = ANY($1::uuid[])",
                [popular_event, new_event, unindexed_event],
            )
            await source.execute("DELETE FROM profiles WHERE id = $1", profile)
            await source.close()
            await journal.execute(
                "DELETE FROM recommendation_pages WHERE session_id = ANY($1::text[])", session_ids
            )
            if revision is not None:
                for table in ("user_embeddings", "event_embeddings", "embedding_index_versions"):
                    await journal.execute(
                        f"DELETE FROM public.{table} WHERE model_name = $1", revision
                    )
                index = await journal.fetchval(
                    """
                    SELECT quote_ident(indexname) FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = 'event_embeddings'
                      AND indexdef LIKE $1
                    """,
                    f"%'{revision}'%",
                )
                if index is not None:
                    await journal.execute(f"DROP INDEX public.{index}")
            await journal.close()
            async with Redis.from_url(integration_redis_url) as redis:
                await redis.delete(*(SessionStore.key(session_id) for session_id in session_ids))

    try:
        first = train_and_register(tmp_path / "catalog", experiment, experiment, "fixture")
        second = train_and_register(tmp_path / "scored", experiment, experiment, "fixture")
        assert first != second
        model_version = client.get_model_version(experiment, first.rsplit("/", 1)[-1])
        run = client.get_run(model_version.run_id)
        assert run.data.tags["dataset_version"] == version
        assert {"validation_log_loss", "test_log_loss"} <= run.data.metrics.keys()

        first_file = prepare_ranker(first, prepared_directory)
        second_file = prepare_ranker(second, prepared_directory)
        with socket.socket() as unavailable, monkeypatch.context() as offline:
            unavailable.bind(("127.0.0.1", 0))
            offline.setenv(
                "MLFLOW_TRACKING_URI", f"http://127.0.0.1:{unavailable.getsockname()[1]}"
            )
            offline.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
            offline.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "1")
            with pytest.raises(mlflow.exceptions.MlflowException):
                prepare_ranker(f"models:/{experiment}/3", prepared_directory)
            assert set(prepared_directory.iterdir()) == {first_file, second_file}
            asyncio.run(serve(first, second))
    finally:
        if client.search_registered_models(filter_string=f"name = '{experiment}'"):
            client.delete_registered_model(experiment)
        registered_experiment = client.get_experiment_by_name(experiment)
        if registered_experiment is not None:
            client.delete_experiment(registered_experiment.experiment_id)
