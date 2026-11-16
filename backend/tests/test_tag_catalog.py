"""Catalog administration and event tag contracts against a disposable database."""

import asyncio
import os
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_personal_scenarios import client, event, user

from dvizh_backend.dto.event import UpdateEventDTO
from dvizh_backend.dto.tag import CategoryCreateDTO, TagUpdateDTO
from dvizh_backend.main import app
from dvizh_backend.services.admin_auth import require_admin


def test_tag_contract_rejects_duplicates_and_more_than_five() -> None:
    from datetime import UTC, datetime

    base = {
        "title": "Test",
        "starts_at": datetime.now(UTC),
        "format": "ONLINE",
        "online_url": "https://example.org/live",
    }
    repeated = uuid4()
    for values in ([repeated, repeated], [uuid4() for _ in range(6)]):
        with pytest.raises(ValidationError):
            UpdateEventDTO(**base, tag_ids=values)
    with pytest.raises(ValidationError):
        UpdateEventDTO(**base, tags=["arbitrary"])
    with pytest.raises(ValidationError):
        CategoryCreateDTO(name="Test", color="red")
    with pytest.raises(ValidationError):
        TagUpdateDTO(name=None)
    with pytest.raises(ValidationError):
        TagUpdateDTO(slug="new-slug")


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires isolated PostgreSQL")
def test_catalog_crud_and_event_tag_rules() -> None:
    async def scenario() -> None:
        app.dependency_overrides[require_admin] = lambda: None
        try:
            async with client() as (http, _database):
                initial = await http.get("/api/tags")
                assert initial.status_code == 200
                assert any(category["tags"] for category in initial.json())
                suffix = uuid4().hex
                response = await http.post(
                    "/api/admin/tag-categories",
                    json={
                        "name": "Test category " + suffix,
                        "color": "#123456",
                    },
                )
                assert response.status_code == 201, response.text
                category = response.json()
                response = await http.post(
                    "/api/admin/tags",
                    json={
                        "name": "Test tag",
                        "slug": suffix,
                        "category_id": category["id"],
                    },
                )
                assert response.status_code == 201, response.text
                tag = response.json()
                assert (
                    await http.delete(f"/api/admin/tag-categories/{category['id']}")
                ).status_code == 409
                owner = await user(http)
                card = await event(http, owner, tag_ids=[tag["id"]])
                assert card["tags"][0]["category"]["color"] == "#123456"
                filtered = await http.get("/api/events", params={"tag_id": tag["id"]})
                assert filtered.status_code == 200, filtered.text
                assert card["id"] in {item["id"] for item in filtered.json()}
                assert (await http.delete(f"/api/admin/tags/{tag['id']}")).status_code == 409
                assert (
                    await http.patch(
                        f"/api/admin/tags/{tag['id']}",
                        json={
                            "is_active": False,
                            "name": "Renamed tag",
                        },
                    )
                ).status_code == 200
                public = (await http.get("/api/tags")).json()
                assert not any(t["id"] == tag["id"] for c in public for t in c["tags"])
                admin = (await http.get("/api/admin/tags")).json()
                assert any(t["id"] == tag["id"] for c in admin for t in c["tags"])
                body = {
                    "title": card["title"],
                    "starts_at": card["starts_at"],
                    "format": "ONLINE",
                    "online_url": "https://example.org/live",
                    "tag_ids": [tag["id"]],
                }
                response = await http.put(f"/api/events/{card['id']}?actor_id={owner}", json=body)
                assert response.status_code == 200, response.text
                assert response.json()["tags"][0]["name"] == "Renamed tag"
                for invalid in ([tag["id"]], [str(uuid4())]):
                    response = await http.post(
                        "/api/events", json={**body, "organizer_id": owner, "tag_ids": invalid}
                    )
                    assert response.status_code == 422, response.text
                body["tag_ids"] = []
                assert (
                    await http.put(
                        f"/api/events/{card['id']}?actor_id={owner}",
                        json=body,
                    )
                ).status_code == 200
                assert (await http.delete(f"/api/admin/tags/{tag['id']}")).status_code == 204
                assert (
                    await http.delete(f"/api/admin/tag-categories/{category['id']}")
                ).status_code == 204
        finally:
            app.dependency_overrides.pop(require_admin, None)

    asyncio.run(scenario())
