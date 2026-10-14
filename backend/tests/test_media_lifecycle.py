"""HTTP tests require dedicated PostgreSQL and MinIO test instances."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.database.dependencies import get_database_service
from dvizh_backend.database.models import (
    EventFavorite,
    EventInvitation,
    EventManager,
    Friendship,
    MediaAsset,
)
from dvizh_backend.database.models.enums import EventManagerRole, FriendshipStatus
from dvizh_backend.main import app
from dvizh_backend.services.dependencies import get_media_storage
from dvizh_backend.services.media_errors import StorageUnavailableError
from dvizh_backend.storage import MediaStorage

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
TEST_MINIO_ENDPOINT = os.getenv("TEST_MINIO_ENDPOINT")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not TEST_MINIO_ENDPOINT,
    reason="Requires isolated PostgreSQL and MinIO",
)


def png(size: tuple[int, int] = (24, 24)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, "red").save(stream, format="PNG")
    return stream.getvalue()


@asynccontextmanager
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, DatabaseService, MediaStorage]]:
    assert TEST_DATABASE_URL and make_url(TEST_DATABASE_URL).database == "dvizh_media_test"
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        minio_endpoint=TEST_MINIO_ENDPOINT,
        minio_access_key="media_test",
        minio_secret_key="media-test-password",
        minio_bucket="media-test",
        media_max_mib=1,
        media_max_pixels=100_000,
    )
    database, storage = DatabaseService(TEST_DATABASE_URL), MediaStorage(settings)
    overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_database_service] = lambda: database
    app.dependency_overrides[get_media_storage] = lambda: storage
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            yield http, database, storage
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        await database.dispose()


async def user(http: httpx.AsyncClient) -> str:
    response = await http.post(
        "/api/users",
        json={
            "username": "u_" + uuid4().hex,
            "display_name": "Test user",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def event_body(owner: str, **changes: object) -> dict:
    return {
        "organizer_id": owner,
        "title": "Test " + uuid4().hex,
        "starts_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "format": "ONLINE",
        "online_url": "https://example.com/live",
        **changes,
    }


async def event(http: httpx.AsyncClient, owner: str, *, draft: bool = False) -> dict:
    response = await http.post(
        "/api/events/drafts" if draft else "/api/events", json=event_body(owner)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def upload(http: httpx.AsyncClient, owner: str) -> dict:
    response = await http.post(
        f"/api/media?user_id={owner}&filename=photo.png",
        content=png(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_real_upload_avatar_cover_and_draft_media_privacy() -> None:
    async def scenario() -> None:
        async with client() as (http, _, storage):
            owner, stranger = await user(http), await user(http)
            asset = await upload(http, owner)
            assert asset["content_type"] == "image/webp"
            assert "bucket" not in asset and "object_key" not in asset
            content_url = asset["content_url"]
            assert (await http.get(content_url)).status_code == 403
            downloaded = await http.get(f"{content_url}?viewer_id={owner}")
            assert downloaded.status_code == 200
            with Image.open(BytesIO(downloaded.content)) as image:
                assert image.format == "WEBP" and image.size == (24, 24)
            assert (
                storage.client.stat_object("media-test", f"images/{owner}/{asset['id']}.webp").size
                == asset["size_bytes"]
            )
            assert (
                await http.put(f"/api/users/{stranger}/avatar", json={"media_id": asset["id"]})
            ).status_code == 403
            avatar = await http.put(f"/api/users/{owner}/avatar", json={"media_id": asset["id"]})
            assert avatar.status_code == 200 and avatar.json()["avatar_url"] == content_url
            assert (await http.get(content_url)).status_code == 200
            assert (
                await http.put(f"/api/users/{owner}/avatar", json={"media_id": None})
            ).status_code == 200
            card = await event(http, owner, draft=True)
            cover = await http.put(
                f"/api/events/{card['id']}/cover?actor_id={owner}", json={"media_id": asset["id"]}
            )
            assert cover.status_code == 200 and cover.json()["cover_media_id"] == asset["id"]
            assert (await http.get(content_url)).status_code == 403
            assert (await http.get(f"{content_url}?viewer_id={stranger}")).status_code == 403
            assert (
                await http.post(f"/api/events/{card['id']}/publish", json={"actor_id": owner})
            ).status_code == 200
            assert (await http.get(content_url)).status_code == 200
            assert (
                await http.put(
                    f"/api/events/{card['id']}/cover?actor_id={owner}", json={"media_id": None}
                )
            ).json()["cover_media_id"] is None

    asyncio.run(scenario())


def test_upload_validation_stream_limits_and_storage_compensation() -> None:
    async def scenario() -> None:
        async with client() as (http, database, storage):
            owner = await user(http)
            path = f"/api/media?user_id={owner}"
            assert (
                await http.post(
                    path, content=b"not an image", headers={"Content-Type": "image/png"}
                )
            ).status_code == 415
            assert (await http.post(path, content=png((400, 400)))).status_code == 413
            assert (
                await http.post(path, content=png(), headers={"Content-Length": "-1"})
            ).status_code == 400
            assert (
                await http.post(path, content=png(), headers={"Content-Length": "1048577"})
            ).status_code == 413

            async def too_large() -> AsyncIterator[bytes]:
                yield b"x" * 524288
                yield b"x" * 524289

            assert (await http.post(path, content=too_large())).status_code == 413
            original_put = storage.put

            async def put_then_fail(bucket: str, key: str, data: bytes) -> None:
                await original_put(bucket, key, data)
                raise StorageUnavailableError("Simulated failure after upload")

            storage.put = put_then_fail
            assert (await http.post(path, content=png())).status_code == 503
            assert list(storage.client.list_objects("media-test", prefix=f"images/{owner}/")) == []
            async with database.session() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(MediaAsset)
                        .where(MediaAsset.uploaded_by_user_id == UUID(owner))
                    )
                    == 0
                )

    asyncio.run(scenario())


def test_draft_publish_update_cancel_and_transactional_notifications() -> None:
    async def scenario() -> None:
        async with client() as (http, database, _):
            owner, participant, follower, stranger = [await user(http) for _ in range(4)]
            card = await event(http, owner, draft=True)
            event_id = card["id"]
            assert card["status"] == "DRAFT" and card["published_at"] is None
            assert (await http.get(f"/api/events/{event_id}")).status_code == 403
            assert (await http.get(f"/api/events/{event_id}?viewer_id={owner}")).status_code == 200
            assert (
                await http.get(f"/api/events/{event_id}?viewer_id={stranger}")
            ).status_code == 403
            assert len((await http.get(f"/api/users/{owner}/drafts")).json()) == 1
            assert event_id not in {
                item["id"] for item in (await http.get("/api/events?limit=100")).json()
            }
            assert (
                await http.post(
                    f"/api/events/{event_id}/participants", json={"user_id": participant}
                )
            ).status_code == 409
            assert (
                await http.post(f"/api/events/{event_id}/publish", json={"actor_id": stranger})
            ).status_code == 403
            for _ in range(2):
                assert (
                    await http.post(f"/api/events/{event_id}/publish", json={"actor_id": owner})
                ).json()["status"] == "PUBLISHED"
            assert (await http.get(f"/api/users/{owner}/drafts")).json() == []
            assert (
                await http.post(
                    f"/api/events/{event_id}/participants", json={"user_id": participant}
                )
            ).status_code == 200
            async with database.session() as session:
                session.add_all(
                    [
                        EventFavorite(user_id=UUID(follower), event_id=UUID(event_id)),
                        EventFavorite(user_id=UUID(participant), event_id=UUID(event_id)),
                    ]
                )
            updated = {
                key: card[key]
                for key in (
                    "title",
                    "description",
                    "starts_at",
                    "ends_at",
                    "timezone",
                    "is_all_day",
                    "format",
                    "online_url",
                    "location",
                    "visibility",
                    "join_policy",
                    "tags",
                )
            }
            updated["title"] = "Changed title"
            assert (
                await http.put(f"/api/events/{event_id}?actor_id={stranger}", json=updated)
            ).status_code == 403
            for _ in range(2):
                response = await http.put(f"/api/events/{event_id}?actor_id={owner}", json=updated)
                assert response.status_code == 200, response.text
            notices = (await http.get(f"/api/users/{participant}/notifications")).json()
            assert len(notices) == 1 and notices[0]["kind"] == "EVENT_UPDATED"
            assert notices[0]["payload"]["changed_fields"] == ["title"]
            assert len((await http.get(f"/api/users/{follower}/notifications")).json()) == 1
            assert (await http.get(f"/api/users/{owner}/notifications")).json() == []
            assert (
                await http.put(f"/api/users/{stranger}/notifications/{notices[0]['id']}/read")
            ).status_code == 403
            for _ in range(2):
                assert (
                    await http.put(
                        f"/api/users/{participant}/notifications/{notices[0]['id']}/read"
                    )
                ).json()["read_at"] is not None
            assert (
                await http.get(f"/api/users/{participant}/notifications?unread_only=true")
            ).json() == []
            for _ in range(2):
                response = await http.post(
                    f"/api/events/{event_id}/cancel", json={"actor_id": owner}
                )
                assert response.status_code == 200, response.text
            assert (await http.get(f"/api/users/{participant}/calendar")).json() == []
            assert (
                await http.post(f"/api/events/{event_id}/participants", json={"user_id": stranger})
            ).status_code == 409
            assert len((await http.get(f"/api/users/{participant}/notifications")).json()) == 2
            assert (
                await http.post(f"/api/events/{event_id}/publish", json={"actor_id": owner})
            ).status_code == 409

    asyncio.run(scenario())


def test_manager_draft_access_cover_and_cancel_permissions() -> None:
    async def scenario() -> None:
        async with client() as (http, database, _):
            owner, manager, stranger = [await user(http) for _ in range(3)]
            card = await event(http, owner, draft=True)
            async with database.session() as session:
                session.add(
                    EventManager(
                        event_id=UUID(card["id"]),
                        user_id=UUID(manager),
                        role=EventManagerRole.MANAGER,
                    )
                )
            assert (
                await http.get(f"/api/events/{card['id']}?viewer_id={manager}")
            ).status_code == 200
            asset = await upload(http, manager)
            assert (
                await http.put(
                    f"/api/events/{card['id']}/cover?actor_id={manager}",
                    json={"media_id": asset["id"]},
                )
            ).status_code == 200
            assert (
                await http.post(f"/api/events/{card['id']}/cancel", json={"actor_id": stranger})
            ).status_code == 403
            assert (
                await http.post(f"/api/events/{card['id']}/cancel", json={"actor_id": manager})
            ).json()["status"] == "CANCELLED"
            assert (
                await http.put(
                    f"/api/events/{card['id']}/cover?actor_id={manager}", json={"media_id": None}
                )
            ).status_code == 409

    asyncio.run(scenario())


def test_friends_and_private_cover_access() -> None:
    async def scenario() -> None:
        async with client() as (http, database, _):
            owner, friend, stranger = [await user(http) for _ in range(3)]
            asset = await upload(http, owner)
            response = await http.post("/api/events", json=event_body(owner, visibility="FRIENDS"))
            card = response.json()
            assert (
                await http.put(
                    f"/api/events/{card['id']}/cover?actor_id={owner}",
                    json={"media_id": asset["id"]},
                )
            ).status_code == 200
            async with database.session() as session:
                low, high = sorted([UUID(owner), UUID(friend)], key=lambda value: value.int)
                session.add(
                    Friendship(
                        user_low_id=low,
                        user_high_id=high,
                        requested_by_user_id=UUID(owner),
                        status=FriendshipStatus.ACCEPTED,
                    )
                )
            assert (await http.get(f"{asset['content_url']}?viewer_id={friend}")).status_code == 200
            assert (
                await http.get(f"{asset['content_url']}?viewer_id={stranger}")
            ).status_code == 403
            private_asset = await upload(http, owner)
            response = await http.post("/api/events", json=event_body(owner, visibility="PRIVATE"))
            card = response.json()
            assert (
                await http.put(
                    f"/api/events/{card['id']}/cover?actor_id={owner}",
                    json={"media_id": private_asset["id"]},
                )
            ).status_code == 200
            assert (
                await http.get(f"{private_asset['content_url']}?viewer_id={friend}")
            ).status_code == 403
            async with database.session() as session:
                session.add(
                    EventInvitation(
                        occurrence_id=UUID(card["occurrence_id"]),
                        inviter_user_id=UUID(owner),
                        invitee_user_id=UUID(friend),
                    )
                )
            assert (
                await http.get(f"{private_asset['content_url']}?viewer_id={friend}")
            ).status_code == 200

    asyncio.run(scenario())
