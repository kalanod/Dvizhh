"""Settings UI schema and command orchestration; domain rules stay in their services."""

import re
from uuid import UUID

from pydantic import ValidationError

from dvizh_backend.api.schemas.account import ChangePasswordCommand
from dvizh_backend.api.schemas.settings import (
    ButtonElement,
    InputElement,
    SelectElement,
    SelectOption,
    SettingsActionResponse,
    SettingsCard,
    SettingsDocument,
    SettingsRow,
    SettingsTab,
    TextElement,
    ToggleElement,
)
from dvizh_backend.api.schemas.tag import (
    CategoryCreateDTO,
    CategoryUpdateDTO,
    TagCreateDTO,
    TagUpdateDTO,
)
from dvizh_backend.services.account_context import AccountRequestContext

from .tag_service import TagService
from .user_service import UserService


class SettingsInputError(Exception):
    pass


class SettingsActionNotFoundError(Exception):
    pass


def text(text_id: str, value: str) -> TextElement:
    return TextElement(id=text_id, text=value)


def input_field(field_id: str, label: str, value: str = "", **options) -> InputElement:
    return InputElement(id=field_id, label=label, value=value, **options)


def button(
    action_id: str, label: str, *, delete: bool = False, changed: bool = False
) -> ButtonElement:
    return ButtonElement(
        id="delete" if delete else "save",
        action_id=action_id,
        label=label,
        tone="danger" if delete else "primary",
        validate_fields=not delete,
        confirmation="Удалить запись? Это действие нельзя отменить." if delete else None,
        rows="changed" if changed else "all",
    )


def order_field(value: int = 0) -> InputElement:
    return input_field("sort_order", "Порядок", str(value), pattern=r"-?[0-9]+", max_length=11)


class SettingsService:
    def __init__(self, tags: TagService, users: UserService) -> None:
        self.tags, self.users = tags, users

    async def document(self) -> SettingsDocument:
        catalog = await self.tags.catalog(include_inactive=True)
        security = SettingsRow(
            id="security.password",
            elements=[
                input_field(
                    "current_password",
                    "Текущий пароль",
                    input_type="password",
                    min_length=1,
                    max_length=128,
                    autocomplete="current-password",
                ),
                input_field(
                    "new_password",
                    "Новый пароль",
                    input_type="password",
                    min_length=8,
                    max_length=128,
                    autocomplete="new-password",
                    hint="От 8 до 128 символов. Сервер может требовать более длинный пароль.",
                ),
                input_field(
                    "confirm_password",
                    "Повторите новый пароль",
                    input_type="password",
                    max_length=128,
                    matches="new_password",
                    autocomplete="new-password",
                ),
            ],
        )
        category_rows = [
            SettingsRow(
                id="category.create",
                elements=[
                    input_field("name", "Название", max_length=120),
                    input_field(
                        "color",
                        "Цвет",
                        "#808080",
                        pattern="#[0-9A-Fa-f]{6}",
                        max_length=7,
                        hint="HEX, например #808080",
                    ),
                    order_field(),
                ],
            )
        ]
        tag_rows = []
        options = [
            SelectOption(value=str(category.id), label=category.name) for category in catalog
        ]
        if options:
            tag_rows.append(
                SettingsRow(
                    id="tag.create",
                    elements=[
                        input_field("name", "Название", max_length=120),
                        input_field(
                            "slug",
                            "Код тематики",
                            max_length=80,
                            hint="Постоянный уникальный код; после создания не меняется.",
                        ),
                        SelectElement(
                            id="category_id",
                            label="Категория",
                            value=options[0].value,
                            options=options,
                        ),
                        ToggleElement(id="is_active", label="Активен", value=True),
                        order_field(),
                    ],
                )
            )
        else:
            tag_rows.append(
                SettingsRow(
                    id="tag.empty",
                    elements=[
                        TextElement(id="title", text="Сначала создайте категорию.", tone="muted"),
                    ],
                )
            )
        for category in catalog:
            category_id = f"category.{category.id}"
            category_rows.append(
                SettingsRow(
                    id=category_id,
                    elements=[
                        text("title", category.name),
                        input_field("name", "Название", category.name, max_length=120),
                        input_field(
                            "color", "Цвет", category.color, pattern="#[0-9A-Fa-f]{6}", max_length=7
                        ),
                        order_field(category.sort_order),
                        button(f"category.delete.{category.id}", "Удалить", delete=True),
                    ],
                )
            )
            for tag in category.tags:
                tag_rows.append(
                    SettingsRow(
                        id=f"tag.{tag.id}",
                        elements=[
                            text("title", f"{tag.name} · {tag.slug}"),
                            input_field("name", "Название", tag.name, max_length=120),
                            SelectElement(
                                id="category_id",
                                label="Категория",
                                value=str(category.id),
                                options=options,
                            ),
                            ToggleElement(id="is_active", label="Активен", value=tag.is_active),
                            order_field(tag.sort_order),
                            button(f"tag.delete.{tag.id}", "Удалить", delete=True),
                        ],
                    )
                )
        return SettingsDocument(
            tabs=[
                SettingsTab(
                    id="security",
                    label="Безопасность",
                    cards=[SettingsCard(
                        id="security.password", title="Смена своего пароля", rows=[security],
                        actions=[button("security.password", "Сменить пароль")],
                    )],
                ),
                SettingsTab(
                    id="categories",
                    label="Категории",
                    cards=[
                        SettingsCard(
                            id="categories.create", title="Новая категория",
                            rows=category_rows[:1], actions=[button("category.create", "Создать")],
                        ),
                        SettingsCard(
                            id="categories.edit", title="Категории", rows=category_rows[1:],
                            actions=[button("category.save", "Сохранить все", changed=True)],
                        ),
                    ],
                ),
                SettingsTab(
                    id="tags",
                    label="Тематики",
                    cards=[
                        SettingsCard(
                            id="tags.create", title="Новая тематика", rows=tag_rows[:1],
                            actions=[button("tag.create", "Создать")] if options else [],
                        ),
                        SettingsCard(
                            id="tags.edit", title="Тематики", rows=tag_rows[1:],
                            description="Используемые тематики можно отключить.",
                            actions=[button("tag.save", "Сохранить все", changed=True)],
                        ),
                    ],
                ),
            ]
        )

    async def execute(
        self, action_id: str, rows: dict[str, dict[str, str | bool]], context: AccountRequestContext
    ) -> SettingsActionResponse:
        document = await self.document()
        allowed = {}
        for tab in document.tabs:
            for card in tab.cards:
                for action in card.actions:
                    allowed[action.action_id] = (action, card.rows)
                for row in card.rows:
                    for action in row.elements:
                        if isinstance(action, ButtonElement):
                            allowed[action.action_id] = (action, [row])
        target = allowed.get(action_id)
        if target is None:
            raise SettingsActionNotFoundError("Настройка больше недоступна. Обновите страницу.")
        action, target_rows = target
        row_lookup = {row.id: row for row in target_rows}
        if not rows or (
            (action.rows == "changed" and not set(rows) <= set(row_lookup))
            or (action.rows == "all" and set(rows) != set(row_lookup))
        ):
            raise SettingsInputError("Набор строк не соответствует действию настроек.")
        deleting = ".delete." in action_id
        prepared = []
        try:
            # Prepare every typed command before the first mutation. Domain errors later
            # propagate to the request transaction and roll back the entire batch.
            for row_id, values in rows.items():
                fields = {
                    element.id: element for element in row_lookup[row_id].elements
                    if isinstance(element, InputElement | SelectElement | ToggleElement)
                }
                if set(values) != set(fields):
                    raise SettingsInputError("Набор полей не соответствует строке настроек.")
                if not deleting:
                    self._validate(fields, values)
                command_id = action_id
                if action.rows == "changed":
                    kind, entity = row_id.split(".", 1)
                    command_id = f"{kind}.update.{entity}"
                prepared.append(self._prepare(command_id, values))
        except (ValidationError, ValueError, OverflowError):
            raise SettingsInputError("Проверьте формат и допустимые значения полей.") from None
        for command_id, data in prepared:
            await self._dispatch(command_id, data, context)
        return SettingsActionResponse(
            message="Изменения сохранены.", document=await self.document(), applied_rows=list(rows)
        )

    @staticmethod
    def _validate(fields: dict, values: dict[str, str | bool]) -> None:
        for field_id, element in fields.items():
            value = values[field_id]
            if isinstance(element, ToggleElement):
                valid = type(value) is bool
            elif not isinstance(value, str):
                valid = False
            elif isinstance(element, SelectElement):
                valid = value in {option.value for option in element.options}
            else:
                valid = (
                    (not element.required or bool(value))
                    and (element.min_length is None or len(value) >= element.min_length)
                    and (element.max_length is None or len(value) <= element.max_length)
                    and (
                        element.pattern is None or re.fullmatch(element.pattern, value) is not None
                    )
                    and (element.matches is None or value == values[element.matches])
                )
            if not valid:
                raise SettingsInputError(f"Проверьте поле «{element.label}».")

    @staticmethod
    def _prepare(action_id: str, values: dict[str, str | bool]) -> tuple[str, object]:
        if action_id == "security.password":
            return action_id, ChangePasswordCommand(
                current_password=values["current_password"],
                new_password=values["new_password"],
            )
        kind, operation, *_ = action_id.split(".")
        if operation == "delete":
            return action_id, None
        sort_order = int(values["sort_order"])
        if not -(2**31) <= sort_order <= 2**31 - 1:
            raise ValueError("sort_order is outside the database integer range")
        data = {**values, "sort_order": sort_order}
        dto = {
            ("category", "create"): CategoryCreateDTO,
            ("category", "update"): CategoryUpdateDTO,
            ("tag", "create"): TagCreateDTO,
            ("tag", "update"): TagUpdateDTO,
        }[(kind, operation)]
        return action_id, dto.model_validate(data)

    async def _dispatch(
        self, action_id: str, data: object, context: AccountRequestContext
    ) -> None:
        if action_id == "security.password":
            await self.users.change_password(data, context)
            return
        kind, operation, *entity = action_id.split(".")
        entity_id = UUID(entity[0]) if entity else None
        if operation == "delete":
            if kind == "category":
                await self.tags.delete_category(entity_id)
            else:
                await self.tags.delete_tag(entity_id)
        elif kind == "category":
            if operation == "create":
                await self.tags.create_category(data)
            else:
                await self.tags.update_category(entity_id, data)
        elif operation == "create":
            await self.tags.create_tag(data)
        else:
            await self.tags.update_tag(entity_id, data)
