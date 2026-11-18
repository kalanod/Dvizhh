import asyncio
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from conftest import IntegrationDatabases

from dvizh_recommendation.dataset import DatasetWindow, export_dataset


@pytest.mark.integration
def test_export_checks_participation_at_the_show_for_the_recommended_occurrence(
    integration_databases: IntegrationDatabases,
    tmp_path: Path,
) -> None:
    async def run() -> None:
        shown_at = datetime(2020, 2, 1, 12, tzinfo=UTC)
        day = timedelta(days=1)
        minute = timedelta(minutes=1)
        profile, item, session, click = (uuid4() for _ in range(4))
        request_ids = [uuid4() for _ in range(4)]
        async with AsyncExitStack() as stack:
            writer = await asyncpg.connect(integration_databases.source_admin_url)
            stack.push_async_callback(writer.close)
            source = await asyncpg.connect(integration_databases.source_url)
            stack.push_async_callback(source.close)
            journal = await asyncpg.connect(integration_databases.vector_url)
            stack.push_async_callback(journal.close)
            stack.push_async_callback(
                journal.execute,
                "DELETE FROM recommendation_pages WHERE session_id = $1",
                str(session),
            )
            stack.push_async_callback(writer.execute, "DELETE FROM profiles WHERE id = $1", profile)
            stack.push_async_callback(writer.execute, "DELETE FROM events WHERE id = $1", item)

            async with writer.transaction():
                await writer.execute(
                    "INSERT INTO profiles (id, username, display_name) VALUES ($1, $2, $2)",
                    profile,
                    f"test{profile.hex}",
                )
                await writer.execute(
                    """
                    INSERT INTO events (id, slug, title, description, origin, status, visibility,
                                        format, online_url, organizer_user_id)
                    VALUES ($1, $2, 'Dataset test', 'Dataset test', 'USER', 'PUBLISHED',
                            'PUBLIC', 'ONLINE', 'https://example.invalid/dataset', $3)
                    """,
                    item,
                    f"test-{item}",
                    profile,
                )
                occurrences = [
                    await writer.fetchval(
                        """
                        INSERT INTO event_occurrences (event_id, starts_at, timezone, status)
                        VALUES ($1, $2, 'UTC', 'SCHEDULED') RETURNING id
                        """,
                        item,
                        shown_at + (index + 7) * day,
                    )
                    for index in range(4)
                ]
                # The first actual impression had no occurrence ID in the client payload.
                await writer.executemany(
                    """
                    INSERT INTO event_interactions (user_id, event_id, occurrence_id, type,
                        request_id, session_id, interaction_id, occurred_at, received_at)
                    VALUES ($1, $2, $3, 'IMPRESSION', $4, $5, $6, $7, $7)
                    """,
                    [
                        (profile, item, occurrence, request, session, uuid4(), shown_at)
                        for occurrence, request in zip(
                            [None, *occurrences[1:]], request_ids, strict=True
                        )
                    ],
                )
                await writer.execute(
                    """
                    INSERT INTO event_interactions (user_id, event_id, occurrence_id, type,
                        request_id, session_id, interaction_id, occurred_at, received_at)
                    VALUES ($1, $2, $3, 'JOIN_CLICK', $4, $5, $6, $7, $7)
                    """,
                    profile,
                    item,
                    occurrences[3],
                    request_ids[3],
                    session,
                    click,
                    shown_at + minute,
                )
                for occurrence, joined_at, cancelled_at, origin in (
                    (occurrences[0], shown_at - day, shown_at + minute, None),
                    (occurrences[2], shown_at - day, shown_at - minute, None),
                    (occurrences[3], shown_at + 2 * minute, None, click),
                ):
                    participation = await writer.fetchval(
                        """
                        INSERT INTO event_participations (occurrence_id, user_id, status,
                                                          joined_at, cancelled_at, created_at)
                        VALUES ($1, $2, $3, $4, $5, $4) RETURNING id
                        """,
                        occurrence, profile, "CANCELLED" if cancelled_at else "GOING",
                        joined_at, cancelled_at,
                    )
                    await writer.execute(
                        """
                        INSERT INTO participation_status_history (participation_id, to_status,
                                                                  changed_at, origin_interaction_id)
                        VALUES ($1, 'GOING', $2, $3)
                        """,
                        participation, joined_at, origin,
                    )
                    if cancelled_at is not None:
                        await writer.execute(
                            """
                            INSERT INTO participation_status_history
                                (participation_id, from_status, to_status, changed_at)
                            VALUES ($1, 'GOING', 'CANCELLED', $2)
                            """,
                            participation, cancelled_at,
                        )

            await journal.executemany(
                """
                INSERT INTO recommendation_pages
                    (request_id, session_id, user_id, served_at, parameters_hash, items)
                VALUES ($1, $2, $3, $4, 'test', $5)
                """,
                [
                    (str(request), str(session), str(profile), shown_at - minute, json.dumps([{
                        "item_id": str(item),
                        "occurrence_id": str(occurrence),
                        "feature_version": "catalog-v1",
                        "features": {"join_policy": "OPEN"},
                    }]))
                    for request, occurrence in zip(request_ids, occurrences, strict=True)
                ],
            )
            output = tmp_path / "dataset"
            window = DatasetWindow(
                shown_at - day, shown_at + 2 * day, shown_at + 3 * day, shown_at + 4 * day, day
            )
            await export_dataset(source, journal, output, window, "catalog-v1")
            labels = {
                row["request_id"]: row["label"]
                for row in map(json.loads, (output / "examples.jsonl").read_text().splitlines())
                if row["request_id"] in {str(request_id) for request_id in request_ids}
            }
            assert labels == {
                str(request_ids[1]): 0,
                str(request_ids[2]): 0,
                str(request_ids[3]): 1,
            }

    asyncio.run(run())
