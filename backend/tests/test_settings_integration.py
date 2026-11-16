"""Settings commands using real domain services and a disposable migrated database."""

import asyncio
import os
from uuid import uuid4

import pytest
from test_personal_scenarios import client

from dvizh_backend.services import admin_auth


def values(row: dict) -> dict:
    return {
        element["id"]: element["value"]
        for element in row["elements"]
        if element["type"] in {"input", "select", "toggle"}
    }


def rows(document: dict) -> list[dict]:
    return [row for tab in document["tabs"] for card in tab["cards"] for row in card["rows"]]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_settings_catalog_round_trip_and_domain_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_auth,
        "_fetch_account",
        lambda *_: admin_auth.AdminAccount(
            id=uuid4(),
            role="admin",
        ),
    )

    async def scenario() -> None:
        async with client() as (http, _database):
            http.cookies.set("dvizh_access", "disposable-test-token")
            http.headers.update({"X-Dvizh-Admin": "1", "X-Dvizh-Account": "1"})
            name = "Settings " + uuid4().hex

            async def execute(action: str, fields: dict, status: int = 200) -> dict:
                action_id = action.split(".")[0] + ".save" if ".update." in action else action
                row_id = action.replace(".update.", ".").replace(".delete.", ".")
                response = await http.post(
                    f"/api/settings/actions/{action_id}",
                    json={
                        "schema_version": 2,
                        "rows": {row_id: fields},
                    },
                )
                assert response.status_code == status, response.text
                return response.json()

            document = (await http.get("/api/settings")).json()
            assert document["schema_version"] == 2
            result = await execute(
                "category.create",
                {
                    "name": name,
                    "color": "#135790",
                    "sort_order": "-3",
                },
            )
            category_row = next(
                row
                for row in rows(result["document"])
                if row["id"].startswith("category.") and values(row).get("name") == name
            )
            category_id = category_row["id"].removeprefix("category.")
            second_name = "Batch second " + uuid4().hex
            result = await execute("category.create", {
                "name": second_name, "color": "#246802", "sort_order": "0",
            })
            second_row = next(
                row for row in rows(result["document"]) if values(row).get("name") == second_name
            )
            conflict_name = "Batch conflict " + uuid4().hex
            response = await http.post("/api/settings/actions/category.save", json={
                "schema_version": 2,
                "rows": {
                    category_row["id"]: {**values(category_row), "name": conflict_name},
                    second_row["id"]: {**values(second_row), "name": conflict_name},
                },
            })
            assert response.status_code == 409, response.text
            refreshed = (await http.get("/api/settings")).json()
            names = {row["id"]: values(row).get("name") for row in rows(refreshed)}
            assert names[category_row["id"]] == name
            assert names[second_row["id"]] == second_name
            # A dirty subset changes exactly one row and reports its ID.
            response = await http.post("/api/settings/actions/category.save", json={
                "schema_version": 2,
                "rows": {second_row["id"]: {**values(second_row), "sort_order": "4"}},
            })
            assert response.status_code == 200, response.text
            assert response.json()["applied_rows"] == [second_row["id"]]
            await execute(
                "category.delete." + second_row["id"].removeprefix("category."), values(second_row)
            )
            result = await execute(
                "tag.create",
                {
                    "name": "Test tag",
                    "slug": uuid4().hex,
                    "category_id": category_id,
                    "is_active": True,
                    "sort_order": "0",
                },
            )
            tag_row = next(
                row
                for row in rows(result["document"])
                if values(row).get("category_id") == category_id and row["id"] != "tag.create"
            )
            tag_id = tag_row["id"].removeprefix("tag.")
            await execute(f"category.delete.{category_id}", values(category_row), 409)
            result = await execute(
                f"tag.update.{tag_id}",
                {
                    **values(tag_row),
                    "name": "Renamed",
                    "is_active": False,
                },
            )
            tag_row = next(row for row in rows(result["document"]) if row["id"] == f"tag.{tag_id}")
            assert values(tag_row)["is_active"] is False
            assert values(tag_row)["name"] == "Renamed"
            await execute(
                f"category.update.{category_id}",
                {
                    **values(category_row),
                    "sort_order": "9999999999",
                },
                422,
            )
            result = await execute(f"tag.delete.{tag_id}", values(tag_row))
            assert not any(row["id"] == f"tag.{tag_id}" for row in rows(result["document"]))
            result = await execute(f"category.delete.{category_id}", values(category_row))
            assert not any(
                row["id"] == f"category.{category_id}" for row in rows(result["document"])
            )

    asyncio.run(scenario())
