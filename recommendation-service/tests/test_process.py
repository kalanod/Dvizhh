from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import asyncpg
import grpc
import pytest
from redis import Redis

from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated import recommendation_service_pb2_grpc
from dvizh_recommendation.pagination import SessionStore

if TYPE_CHECKING:
    from conftest import IntegrationDatabases


pytestmark = pytest.mark.integration


def test_server_process_serves_paginated_recommendations_and_stops_cleanly(
    integration_databases: IntegrationDatabases,
    integration_redis_url: str,
) -> None:
    profile_id = uuid4()
    item_ids = [uuid4() for _ in range(105)]
    session_id = uuid4().hex
    hidden_ids: set[UUID] = set()

    async def prepare_catalog() -> int:
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, $3)",
                    profile_id,
                    f"process-test-{profile_id.hex}",
                    "Process test organizer",
                )
                now = datetime.now(UTC)
                await connection.executemany(
                    """
                    INSERT INTO events (
                        id, slug, title, description, origin, status, visibility,
                        format, online_url, organizer_user_id, published_at
                    ) VALUES (
                        $1, $2, 'Process test', 'Process test', 'USER', 'PUBLISHED',
                        'PUBLIC', 'ONLINE', 'https://example.invalid/process-test', $3, $4
                    )
                    """,
                    [
                        (
                            item_id,
                            f"process-test-{item_id.hex}",
                            profile_id,
                            now - timedelta(seconds=i),
                        )
                        for i, item_id in enumerate(item_ids)
                    ],
                )
                await connection.executemany(
                    """
                    INSERT INTO event_occurrences (
                        id, event_id, starts_at, ends_at, timezone, status
                    ) VALUES ($1, $2, $3, $4, 'UTC', 'SCHEDULED')
                    """,
                    [
                        (
                            uuid4(),
                            item_id,
                            now + timedelta(days=5),
                            now + timedelta(days=5, hours=2),
                        )
                        for item_id in item_ids
                    ],
                )
                return await connection.fetchval("SELECT COUNT(*) FROM events")
        finally:
            await connection.close()

    async def remove_catalog() -> None:
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE events SET visibility = 'PUBLIC' WHERE id = ANY($1::uuid[])",
                    list(hidden_ids),
                )
                await connection.execute("DELETE FROM events WHERE id = ANY($1::uuid[])", item_ids)
                await connection.execute("DELETE FROM profiles WHERE id = $1", profile_id)
        finally:
            await connection.close()

    async def make_private(ids: list[UUID]) -> None:
        hidden_ids.update(ids)
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            await connection.execute(
                "UPDATE events SET visibility = 'PRIVATE' WHERE id = ANY($1::uuid[])", ids
            )
        finally:
            await connection.close()

    service_dir = Path(__file__).resolve().parents[1]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    address = f"127.0.0.1:{port}"
    environment = {
        **os.environ,
        "GRPC_BIND_ADDRESS": address,
        "SOURCE_DATABASE_URL": integration_databases.source_url,
        "VECTOR_DATABASE_URL": integration_databases.vector_url,
        "REDIS_URL": integration_redis_url,
        "REDIS_TIMEOUT_SECONDS": "2",
        "DATABASE_TIMEOUT_SECONDS": "2",
        "SHUTDOWN_GRACE_SECONDS": "1",
    }
    healthcheck_command = [sys.executable, "-m", "dvizh_recommendation.healthcheck"]

    process = None
    try:
        catalog_count = asyncio.run(prepare_catalog())
        process = subprocess.Popen(
            [sys.executable, "-m", "dvizh_recommendation.main"],
            cwd=service_dir,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)

            healthcheck = subprocess.run(
                healthcheck_command,
                cwd=service_dir,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert healthcheck.returncode == 0, healthcheck.stdout + healthcheck.stderr

            stub = recommendation_service_pb2_grpc.RecommendationServiceStub(channel)
            request = pb.GetRecommendationsRequest(
                user_id=str(profile_id), session_id=session_id, request_id=uuid4().hex, page_size=30
            )
            page = stub.GetRecommendations(request, timeout=5)
            request.request_id = uuid4().hex
            assert stub.GetRecommendations(request, timeout=5) == page
            stub.RefreshSession(
                pb.RefreshSessionRequest(user_id=request.user_id, session_id=session_id), timeout=5
            )

            collected = [item.item_id for item in page.items]
            pages = [page]
            for _ in range((catalog_count + 29) // 30):
                if not page.HasField("next_page_token"):
                    break
                assert len(page.items) == 30
                request.page_token = page.next_page_token
                request.request_id = uuid4().hex
                page = stub.GetRecommendations(request, timeout=5)
                pages.append(page)
                collected.extend(item.item_id for item in page.items)
            assert not page.HasField("next_page_token")
            assert len(collected) == len(set(collected))
            expected = [str(item_id) for item_id in item_ids]
            own_ids = set(expected)
            assert [item_id for item_id in collected if item_id in own_ids] == expected

            first, second = pages[:2]
            hidden_id = second.items[5].item_id
            asyncio.run(make_private([UUID(hidden_id)]))
            request.page_token = first.next_page_token
            filtered = stub.GetRecommendations(request, timeout=5)
            assert [item.item_id for item in filtered.items] == [
                item.item_id for item in second.items if item.item_id != hidden_id
            ]
            assert filtered.next_page_token == second.next_page_token
            assert stub.GetRecommendations(request, timeout=5) == filtered

            asyncio.run(make_private([UUID(item.item_id) for item in first.items]))
            request.ClearField("page_token")
            empty = stub.GetRecommendations(request, timeout=5)
            assert not empty.items
            assert empty.next_page_token == first.next_page_token
            request.page_token = empty.next_page_token
            assert stub.GetRecommendations(request, timeout=5) == filtered

        process.terminate()
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output
        assert (
            subprocess.run(
                healthcheck_command, cwd=service_dir, env=environment, timeout=5
            ).returncode
            == 1
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        try:
            with Redis.from_url(integration_redis_url) as redis:
                redis.delete(SessionStore.key(session_id))
        finally:
            asyncio.run(remove_catalog())
