from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Slug = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class CategoryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    sort_order: int


class TagDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    slug: str
    name: str
    is_active: bool
    sort_order: int


class EventTagDTO(BaseModel):
    id: UUID
    slug: str
    name: str
    is_active: bool
    category: CategoryDTO


class CategoryTagsDTO(CategoryDTO):
    tags: list[TagDTO]


class CategoryCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    color: Color
    sort_order: int = 0


class CategoryUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    color: Color | None = None
    sort_order: int | None = None

    @field_validator("name", "color", "sort_order")
    @classmethod
    def not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class TagCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    slug: Slug
    name: Name
    is_active: bool = True
    sort_order: int = 0

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.lower()


class TagUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID | None = None
    name: Name | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("category_id", "name", "is_active", "sort_order")
    @classmethod
    def not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value
