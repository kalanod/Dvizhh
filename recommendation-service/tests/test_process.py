from __future__ import annotations

import asyncio
import json
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

from dvizh_recommendation.dataset import DatasetWindow, export_dataset
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated import recommendation_service_pb2_grpc
from dvizh_recommendation.pagination import SessionStore

if TYPE_CHECKING:
    from conftest import IntegrationDatabases


pytestmark = pytest.mark.integration


async def verify_feedback_export(
    databases: IntegrationDatabases,
    output: Path,
    session_id: str,
    request_id: str,
    returned_ids: list[str],
    calculated_at: datetime,
    initial_starts_at: datetime,
) -> None:
    source = await asyncpg.connect(databases.source_admin_url)
    journal = await asyncpg.connect(databases.vector_url)
    try:
        page = await journal.fetchrow(
            "SELECT user_id, served_at, items FROM recommendation_pages WHERE request_id = $1",
            str(UUID(request_id)),
        )
        assert page is not None
        items = json.loads(page["items"])
        assert [item["item_id"] for item in items] == returned_ids
        registered, skipped, awaiting_window = items[:3]
        assert datetime.fromisoformat(registered["calculated_at"]) == calculated_at
        assert registered["features"]["hours_until_start"] == pytest.approx(
            (initial_starts_at - calculated_at).total_seconds() / 3600
        )
        assert await source.fetchval(
            "SELECT starts_at FROM event_occurrences WHERE id = $1",
            UUID(registered["occurrence_id"]),
        ) == initial_starts_at + timedelta(hours=3)
        served_at = page["served_at"]
        seen_at = served_at + timedelta(seconds=1)
        first_click = uuid4()
        interaction = """
            INSERT INTO event_interactions (
                interaction_id, user_id, event_id, occurrence_id, session_id, request_id,
                type, occurred_at, received_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::interaction_type, $8, $9)
        """

        async def record(
            identifier: UUID,
            item: dict,
            kind: str,
            when: datetime,
            *,
            clock_offset: timedelta = timedelta(0),
        ) -> None:
            await source.execute(
                interaction,
                identifier,
                UUID(page["user_id"]),
                UUID(item["item_id"]),
                UUID(item["occurrence_id"]),
                UUID(session_id),
                UUID(request_id),
                kind,
                when + clock_offset,
                when,
            )

        async with source.transaction():
            browser_clock_offset = timedelta(hours=4)
            await record(
                uuid4(), registered, "IMPRESSION", seen_at, clock_offset=browser_clock_offset
            )
            await record(
                uuid4(),
                registered,
                "IMPRESSION",
                seen_at + timedelta(seconds=1),
                clock_offset=browser_clock_offset,
            )
            await record(uuid4(), skipped, "IMPRESSION", seen_at)
            await record(uuid4(), awaiting_window, "IMPRESSION", seen_at + timedelta(hours=5))
            await record(
                first_click,
                registered,
                "JOIN_CLICK",
                seen_at + timedelta(minutes=1),
                clock_offset=browser_clock_offset,
            )
            participation_id = await source.fetchval(
                """
                INSERT INTO event_participations
                    (occurrence_id, user_id, status, origin_interaction_id)
                VALUES ($1, $2, 'GOING', $3) RETURNING id
                """,
                UUID(registered["occurrence_id"]),
                UUID(page["user_id"]),
                first_click,
            )
            await source.execute(
                """
                INSERT INTO participation_status_history
                    (participation_id, from_status, to_status, changed_at, origin_interaction_id)
                VALUES ($1, 'REQUESTED', 'GOING', $2, $3)
                """,
                participation_id,
                seen_at + timedelta(hours=2),
                first_click,
            )

        window = DatasetWindow(
            start=served_at - timedelta(minutes=5),
            validation_start=served_at + timedelta(hours=6),
            test_start=served_at + timedelta(hours=12),
            as_of=served_at + timedelta(days=1),
            observation_window=timedelta(hours=3),
        )
        async with databases.connections() as (reader, pages):
            await export_dataset(reader, pages, output, window, registered["feature_version"])
        rows = [json.loads(line) for line in (output / "examples.jsonl").read_text().splitlines()]
        assert [(row["item_id"], row["label"], row["split"]) for row in rows] == [
            (registered["item_id"], 1, "train"),
            (skipped["item_id"], 0, "train"),
        ]
        assert rows[0]["features"] == registered["features"]
    finally:
        await source.close()
        await journal.close()


def test_server_process_serves_paginated_recommendations_and_stops_cleanly(
    integration_databases: IntegrationDatabases,
    integration_redis_url: str,
    tmp_path: Path,
) -> None:
    profile_id = uuid4()
    item_ids = [uuid4() for _ in range(105)]
    session_id = uuid4().hex
    initial_starts_at = datetime.now(UTC) + timedelta(days=5)
    marker = f"process{profile_id.hex}"

    async def prepare_catalog() -> None:
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
                        $1, $2, $5::text, $5::text, 'USER', 'PUBLISHED',
                        'PUBLIC', 'ONLINE', 'https://example.invalid/process-test', $3, $4
                    )
                    """,
                    [
                        (
                            item_id,
                            f"process-test-{item_id.hex}",
                            profile_id,
                            now - timedelta(seconds=i),
                            marker,
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
                            initial_starts_at,
                            initial_starts_at + timedelta(hours=2),
                        )
                        for item_id in item_ids
                    ],
                )
        finally:
            await connection.close()

    async def remove_catalog() -> None:
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            async with connection.transaction():
                await connection.execute("DELETE FROM events WHERE id = ANY($1::uuid[])", item_ids)
                await connection.execute("DELETE FROM profiles WHERE id = $1", profile_id)
        finally:
            await connection.close()
        journal = await asyncpg.connect(integration_databases.vector_url, timeout=5)
        try:
            await journal.execute(
                "DELETE FROM recommendation_pages WHERE session_id = $1", session_id
            )
        finally:
            await journal.close()

    async def make_private(ids: list[UUID]) -> None:
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            await connection.execute(
                "UPDATE events SET visibility = 'PRIVATE' WHERE id = ANY($1::uuid[])", ids
            )
        finally:
            await connection.close()

    async def read_journal_entry(request_id: str) -> str | None:
        journal = await asyncpg.connect(integration_databases.vector_url, timeout=5)
        try:
            return await journal.fetchval(
                "SELECT to_jsonb(page) FROM recommendation_pages AS page WHERE request_id = $1",
                str(UUID(request_id)),
            )
        finally:
            await journal.close()

    async def replace_occurrence(event_id: UUID) -> None:
        connection = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        try:
            await connection.execute(
                """
                WITH cancelled AS (
                    UPDATE event_occurrences SET status = 'CANCELLED' WHERE event_id = $1
                    RETURNING event_id, starts_at
                )
                INSERT INTO event_occurrences (event_id, starts_at, timezone, status)
                SELECT event_id, starts_at + INTERVAL '1 day', 'UTC', 'SCHEDULED' FROM cancelled
                """,
                event_id,
            )
        finally:
            await connection.close()

    async def add_earlier_occurrence(item_id: UUID, request_id: str) -> datetime:
        source = await asyncpg.connect(integration_databases.source_admin_url, timeout=5)
        journal = await asyncpg.connect(integration_databases.vector_url, timeout=5)
        try:
            canonical_id = str(UUID(request_id))
            pages = await journal.fetch(
                """
                SELECT request_id, items->0->>'calculated_at' AS calculated_at
                FROM recommendation_pages WHERE request_id = ANY($1::text[])
                """,
                [request_id, canonical_id],
            )
            assert [page["request_id"] for page in pages] == [canonical_id]
            await source.execute(
                """
                WITH shifted AS (
                    UPDATE event_occurrences SET starts_at = starts_at + INTERVAL '3 hours',
                      ends_at = ends_at + INTERVAL '3 hours' WHERE event_id = $1
                    RETURNING event_id, starts_at, ends_at, timezone
                )
                INSERT INTO event_occurrences (event_id, starts_at, ends_at, timezone, status)
                SELECT event_id, starts_at - INTERVAL '1 day', ends_at - INTERVAL '1 day',
                       timezone, 'SCHEDULED' FROM shifted
                """,
                item_id,
            )
            return datetime.fromisoformat(pages[0]["calculated_at"])
        finally:
            await source.close()
            await journal.close()

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
        asyncio.run(prepare_catalog())
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
                user_id=profile_id.hex, session_id=session_id, request_id=uuid4().hex, page_size=30
            )
            request.filters["q"].string_value = marker
            page = stub.GetRecommendations(request, timeout=5)
            original_request_id = request.request_id
            request.request_id = str(UUID(original_request_id))
            assert stub.GetRecommendations(request, timeout=5) == page
            request.request_id = original_request_id
            stub.RefreshSession(
                pb.RefreshSessionRequest(user_id=request.user_id, session_id=session_id), timeout=5
            )

            calculated_at = asyncio.run(add_earlier_occurrence(item_ids[30], request.request_id))
            collected = [item.item_id for item in page.items]
            pages = [page]
            request_ids = [request.request_id]
            for _ in range((len(item_ids) + 29) // 30):
                if not page.HasField("next_page_token"):
                    break
                assert len(page.items) == 30
                request.page_token = page.next_page_token
                request.request_id = uuid4().hex
                page = stub.GetRecommendations(request, timeout=5)
                pages.append(page)
                request_ids.append(request.request_id)
                collected.extend(item.item_id for item in page.items)
            assert not page.HasField("next_page_token")
            assert len(collected) == len(set(collected))
            assert collected == [str(item_id) for item_id in item_ids]

            first, second, third = pages[:3]
            hidden_id = second.items[5].item_id
            rescheduled_id = second.items[6].item_id
            request.page_token = first.next_page_token
            request.request_id = request_ids[1]
            assert stub.GetRecommendations(request, timeout=5) == second
            journal_entry = asyncio.run(read_journal_entry(request.request_id))
            assert journal_entry is not None
            request.page_size = 29
            with pytest.raises(grpc.RpcError) as reused:
                stub.GetRecommendations(request, timeout=5)
            assert reused.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            request.page_size = 30

            asyncio.run(make_private([UUID(hidden_id)]))
            asyncio.run(replace_occurrence(UUID(rescheduled_id)))
            with pytest.raises(grpc.RpcError) as changed:
                stub.GetRecommendations(request, timeout=5)
            assert changed.value.code() == grpc.StatusCode.ABORTED
            request.request_id = uuid4().hex
            filtered = stub.GetRecommendations(request, timeout=5)
            assert [item.item_id for item in filtered.items] == [
                item.item_id
                for item in second.items
                if item.item_id not in {hidden_id, rescheduled_id}
            ]
            assert filtered.next_page_token == second.next_page_token
            assert stub.GetRecommendations(request, timeout=5) == filtered
            assert asyncio.run(read_journal_entry(request_ids[1])) == journal_entry
            asyncio.run(
                verify_feedback_export(
                    integration_databases,
                    tmp_path / "dataset",
                    session_id,
                    request.request_id,
                    [item.item_id for item in filtered.items],
                    calculated_at,
                    initial_starts_at,
                )
            )
            request.page_token = filtered.next_page_token
            request.request_id = uuid4().hex
            assert stub.GetRecommendations(request, timeout=5) == third

            asyncio.run(make_private([UUID(item.item_id) for item in first.items]))
            request.ClearField("page_token")
            request.request_id = uuid4().hex
            empty = stub.GetRecommendations(request, timeout=5)
            assert not empty.items
            assert empty.next_page_token == first.next_page_token
            request.page_token = empty.next_page_token
            request.request_id = uuid4().hex
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
