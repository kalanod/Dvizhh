import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dvizh_backend.api import security as admin_auth
from dvizh_backend.api.dependencies import get_settings_service
from dvizh_backend.api.schemas.settings import InputElement, SettingsActionRequest
from dvizh_backend.api.schemas.tag import CategoryTagsDTO, TagDTO
from dvizh_backend.main import app
from dvizh_backend.services.account_context import AccountRequestContext
from dvizh_backend.services.settings_service import (
    SettingsActionNotFoundError,
    SettingsInputError,
    SettingsService,
)


def make_service() -> tuple[SettingsService, CategoryTagsDTO, TagDTO]:
    category_id = uuid4()
    tag = TagDTO(
        id=uuid4(), category_id=category_id, name="Jazz", slug="jazz", is_active=False, sort_order=0
    )
    category = CategoryTagsDTO(
        id=category_id, name="Genres", color="#123456", sort_order=2, tags=[tag]
    )
    tags = SimpleNamespace(
        **{
            name: AsyncMock()
            for name in (
                "create_category",
                "update_category",
                "delete_category",
                "create_tag",
                "update_tag",
                "delete_tag",
            )
        }
    )
    tags.catalog = AsyncMock(return_value=[category])
    users = SimpleNamespace(change_password=AsyncMock())
    return SettingsService(tags, users), category, tag


CONTEXT = AccountRequestContext("opaque-test-token", "testserver", "http://testserver", "1")


def test_document_contains_real_catalog_and_all_primitives_without_secrets() -> None:
    service, category, tag = make_service()
    document = asyncio.run(service.document())
    assert document.schema_version == 2
    assert [tab.id for tab in document.tabs] == ["security", "categories", "tags"]
    rows = [row for tab in document.tabs for card in tab.cards for row in card.rows]
    assert len({row.id for row in rows}) == len(rows)
    cards = [card for tab in document.tabs for card in tab.cards]
    assert len({card.id for card in cards}) == len(cards)
    assert [card.id for card in cards] == [
        "security.password", "categories.create", "categories.edit", "tags.create", "tags.edit"
    ]
    for card in cards:
        assert len({action.id for action in card.actions}) == len(card.actions)
    assert cards[2].actions[0].action_id == "category.save"
    assert cards[2].actions[0].rows == "changed"
    assert all(element.action_id.startswith("category.delete.")
               for row in cards[2].rows for element in row.elements if element.type == "button")
    assert {element.type for row in rows for element in row.elements} == {
        "text",
        "input",
        "select",
        "toggle",
        "button",
    }
    for row in rows:
        assert len({element.id for element in row.elements}) == len(row.elements)
        for element in row.elements:
            if isinstance(element, InputElement) and element.input_type == "password":
                assert element.value == ""
    assert str(category.id) in document.model_dump_json()
    assert str(tag.id) in document.model_dump_json()
    assert CONTEXT.token not in document.model_dump_json()
    service.tags.catalog.assert_awaited_once_with(include_inactive=True)


def test_actions_use_typed_domain_service_and_refresh_schema() -> None:
    async def scenario() -> None:
        service, category, tag = make_service()
        result = await service.execute(
            "tag.save",
            {f"tag.{tag.id}": {
                "name": "Updated",
                "category_id": str(category.id),
                "is_active": True,
                "sort_order": "-2",
            }},
            CONTEXT,
        )
        entity_id, data = service.tags.update_tag.await_args.args
        assert entity_id == tag.id
        assert data.name == "Updated" and data.is_active is True and data.sort_order == -2
        assert result.document.schema_version == 2
        assert result.applied_rows == [f"tag.{tag.id}"]
        assert service.tags.catalog.await_count == 2
        await service.execute(
            "category.create",
            {"category.create": {
                "name": "New",
                "color": "#123456",
                "sort_order": "1",
            }},
            CONTEXT,
        )
        assert service.tags.create_category.await_args.args[0].name == "New"
        # Unsaved invalid values do not affect deleting the server-selected entity.
        await service.execute(
            f"category.delete.{category.id}",
            {f"category.{category.id}": {
                "name": "",
                "color": "bad",
                "sort_order": "not an integer",
            }},
            CONTEXT,
        )
        service.tags.delete_category.assert_awaited_once_with(category.id)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "values",
    [
        {"name": "Name", "category_id": "invalid", "is_active": True, "sort_order": "0"},
        {"name": "Name", "category_id": str(uuid4()), "is_active": "false", "sort_order": "0"},
        {"name": "Name", "is_active": True, "sort_order": "0"},
        {
            "name": "Name",
            "category_id": "bad",
            "is_active": True,
            "sort_order": "0",
            "role": "admin",
        },
    ],
)
def test_forged_or_invalid_values_do_not_reach_domain_service(values: dict) -> None:
    service, _, tag = make_service()
    with pytest.raises(SettingsInputError):
        asyncio.run(service.execute("tag.save", {f"tag.{tag.id}": values}, CONTEXT))
    service.tags.update_tag.assert_not_awaited()


def test_unknown_actions_cannot_dispatch_arbitrary_service_calls() -> None:
    service, _, _ = make_service()
    for action in ("user.delete", f"tag.delete.{uuid4()}", "__dict__", "category.create.extra"):
        with pytest.raises(SettingsActionNotFoundError):
            asyncio.run(service.execute(action, {}, CONTEXT))
    service.tags.delete_tag.assert_not_awaited()
    service.users.change_password.assert_not_awaited()


def test_password_confirmation_and_delegation_without_retaining_secrets() -> None:
    async def scenario() -> None:
        service, _, _ = make_service()
        values = {
            "current_password": " old-secret-value ",
            "new_password": " next-secret-value ",
            "confirm_password": "wrong",
        }
        with pytest.raises(SettingsInputError) as error:
            await service.execute("security.password", {"security.password": values}, CONTEXT)
        assert "next-secret-value" not in str(error.value)
        service.users.change_password.assert_not_awaited()
        values["confirm_password"] = values["new_password"]
        result = await service.execute("security.password", {"security.password": values}, CONTEXT)
        command, context = service.users.change_password.await_args.args
        assert context == CONTEXT
        assert command.new_password.get_secret_value() == " next-secret-value "
        assert "next-secret-value" not in result.model_dump_json()
        assert "old-secret-value" not in result.model_dump_json()

    asyncio.run(scenario())


def test_action_envelope_rejects_other_versions_and_coercion() -> None:
    for body in (
        {"schema_version": 1, "rows": {}},
        {"schema_version": True, "rows": {}},
        {"schema_version": 2.0, "rows": {}},
        {"schema_version": 2, "rows": {"row": {"field": 1}}},
        {"rows": {}},
        {"schema_version": 2, "rows": {}, "role": "admin"},
    ):
        with pytest.raises(ValidationError):
            SettingsActionRequest.model_validate(body)
    command = SettingsActionRequest(schema_version=2, rows={"row": {"new_password": "secret"}})
    assert "secret" not in repr(command)
    for rows in (
        {str(i): {} for i in range(501)},
        {"row": {str(i): "x" for i in range(31)}},
    ):
        with pytest.raises(ValidationError):
            SettingsActionRequest(schema_version=2, rows=rows)


def test_batch_accepts_only_dirty_rows_and_prevalidates_all_commands() -> None:
    async def scenario() -> None:
        service, category, _ = make_service()
        second = category.model_copy(update={"id": uuid4(), "name": "Other", "tags": []})
        service.tags.catalog.return_value = [category, second]
        first_values = {"name": "Changed", "color": "#123456", "sort_order": "0"}
        second_values = {"name": "   ", "color": "#123456", "sort_order": "0"}
        # Generic fields pass, but typed DTO rejects whitespace-only name before any write.
        with pytest.raises(SettingsInputError):
            await service.execute("category.save", {
                f"category.{category.id}": first_values,
                f"category.{second.id}": second_values,
            }, CONTEXT)
        service.tags.update_category.assert_not_awaited()
        second_values["name"] = "Valid"
        second_values["sort_order"] = "9999999999"
        with pytest.raises(SettingsInputError):
            await service.execute("category.save", {
                f"category.{category.id}": first_values,
                f"category.{second.id}": second_values,
            }, CONTEXT)
        service.tags.update_category.assert_not_awaited()
        result = await service.execute("category.save", {
            f"category.{second.id}": {**second_values, "sort_order": "3"},
        }, CONTEXT)
        assert result.applied_rows == [f"category.{second.id}"]
        service.tags.update_category.assert_awaited_once()
        assert service.tags.update_category.await_args.args[0] == second.id

    asyncio.run(scenario())


def test_actions_reject_cross_card_foreign_and_extra_rows() -> None:
    async def scenario() -> None:
        service, category, tag = make_service()
        fields = {"name": "Valid", "color": "#123456", "sort_order": "0"}
        for action, payload in (
            ("category.save", {}),
            ("category.save", {"category.create": fields}),
            ("category.save", {f"category.{uuid4()}": fields}),
            ("category.save", {f"tag.{tag.id}": fields}),
            ("category.create", {f"category.{category.id}": fields}),
            ("category.create", {"category.create": fields, f"category.{category.id}": fields}),
            (f"category.delete.{category.id}", {
                f"category.{category.id}": fields, "category.create": fields,
            }),
        ):
            with pytest.raises(SettingsInputError):
                await service.execute(action, payload, CONTEXT)
        service.tags.update_category.assert_not_awaited()
        service.tags.create_category.assert_not_awaited()
        service.tags.delete_category.assert_not_awaited()

    asyncio.run(scenario())


def test_settings_http_enforces_admin_csrf_and_sanitizes_invalid_secrets(monkeypatch) -> None:
    service, _, _ = make_service()
    role = {"name": "admin"}
    monkeypatch.setattr(
        admin_auth,
        "fetch_current_account",
        lambda *_: admin_auth.AdminAccount(
            id=uuid4(),
            role=role["name"],
        ),
    )
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings_service] = lambda: service
    try:
        # Without the context manager the real database lifespan is not started.
        client = TestClient(app)
        try:
            assert client.get("/api/settings").status_code == 401
            client.cookies.set("dvizh_access", "test-token")
            role["name"] = "user"
            assert client.get("/api/settings").status_code == 403
            role["name"] = "admin"
            response = client.get("/api/settings")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            body = {
                "schema_version": 2,
                "rows": {"security.password": {
                    "current_password": "old-secret-value",
                    "new_password": "next-secret-value",
                    "confirm_password": "next-secret-value",
                }},
            }
            path = "/api/settings/actions/security.password"
            assert client.post(path, json=body).status_code == 403
            headers = {"X-Dvizh-Admin": "1", "X-Dvizh-Account": "1", "Origin": "https://evil.test"}
            assert client.post(path, json=body, headers=headers).status_code == 403
            headers["Origin"] = "http://testserver"
            response = client.post(path, json=body, headers=headers)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert "next-secret-value" not in response.text
            _, context = service.users.change_password.await_args.args
            assert context.token == "test-token" and context.host == "testserver"
            assert context.origin == "http://testserver" and context.write_header == "1"
            role["name"] = "user"
            assert client.post(path, json=body, headers=headers).status_code == 403
            assert service.users.change_password.await_count == 1
            role["name"] = "admin"
            response = client.post(
                path,
                json={
                    "schema_version": 2,
                    "rows": {"security.password": {"new_password": {"private-password": True}}},
                },
                headers=headers,
            )
            assert response.status_code == 422
            assert "private-password" not in response.text
        finally:
            client.close()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
