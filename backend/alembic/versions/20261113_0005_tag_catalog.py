"""Administered categorized tag catalog."""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261113_0005"
down_revision = "20261111_0004"
branch_labels = None
depends_on = None

CATEGORIES = [
    (
        "nature",
        "Природа",
        "#39845A",
        [("hiking", "Походы"), ("barbecue", "Шашлыки"), ("camping", "Кемпинг")],
    ),
    (
        "games",
        "Игры",
        "#7357B8",
        [("board-games", "Настольные игры"), ("video-games", "Видеоигры")],
    ),
    (
        "sport",
        "Спорт",
        "#2877B5",
        [("running", "Бег"), ("cycling", "Велосипед"), ("fitness", "Фитнес")],
    ),
    (
        "culture",
        "Культура",
        "#B65C71",
        [("concerts", "Концерты"), ("cinema", "Кино"), ("exhibitions", "Выставки")],
    ),
    ("learning", "Обучение", "#AD7626", [("lectures", "Лекции"), ("workshops", "Мастер-классы")]),
    ("social", "Общение", "#348687", [("dating", "Знакомства"), ("meetups", "Встречи")]),
]


def identifier(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://dvizzh.space/catalog/{value}"))


def rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    op.create_table(
        "tag_categories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="valid_color"),
    )
    op.rename_table("topics", "tags")
    op.rename_table("event_topics", "event_tags")
    op.drop_index("ix_topics_parent_sort_order", table_name="tags")
    op.drop_constraint(op.f("fk_topics_parent_id_topics"), "tags", type_="foreignkey")
    op.drop_column("tags", "parent_id")
    op.drop_column("tags", "description")
    op.alter_column("event_tags", "topic_id", new_column_name="tag_id")
    rename_constraint("tags", "pk_topics", "pk_tags")
    rename_constraint("tags", "uq_topics_slug", "uq_tags_slug")
    rename_constraint("event_tags", "pk_event_topics", "pk_event_tags")
    rename_constraint(
        "event_tags", "fk_event_topics_event_id_events", "fk_event_tags_event_id_events"
    )
    rename_constraint("event_tags", "fk_event_topics_topic_id_topics", "fk_event_tags_tag_id_tags")
    op.execute("ALTER INDEX ix_topics_active_sort_order RENAME TO ix_tags_active_sort_order")
    op.execute("ALTER INDEX ix_event_topics_topic_event RENAME TO ix_event_tags_tag_event")
    op.add_column("tags", sa.Column("category_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_tags_category_id_tag_categories"),
        "tags",
        "tag_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO tag_categories (id, name, color, sort_order) "
            "VALUES (:id, :name, :color, 100)"
        ),
        {"id": identifier("category/other"), "name": "Прочее", "color": "#667085"},
    )
    connection.execute(
        sa.text("UPDATE tags SET category_id = :id"), {"id": identifier("category/other")}
    )
    op.alter_column("tags", "category_id", nullable=False)
    op.create_index("ix_tags_category_sort_order", "tags", ["category_id", "sort_order"])
    for order, (slug, name, color, tags) in enumerate(CATEGORIES):
        category_id = identifier(f"category/{slug}")
        connection.execute(
            sa.text(
                "INSERT INTO tag_categories (id, name, color, sort_order) "
                "VALUES (:id, :name, :color, :order)"
            ),
            {"id": category_id, "name": name, "color": color, "order": order},
        )
        for tag_order, (tag_slug, tag_name) in enumerate(tags):
            connection.execute(
                sa.text(
                    "INSERT INTO tags (id, category_id, slug, name, sort_order) "
                    "VALUES (:id, :category_id, :slug, :name, :order) "
                    "ON CONFLICT (slug) DO UPDATE SET category_id = EXCLUDED.category_id"
                ),
                {
                    "id": identifier(f"tag/{tag_slug}"),
                    "category_id": category_id,
                    "slug": tag_slug,
                    "name": tag_name,
                    "order": tag_order,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_tags_category_sort_order", table_name="tags")
    op.drop_constraint(op.f("fk_tags_category_id_tag_categories"), "tags", type_="foreignkey")
    op.drop_column("tags", "category_id")
    op.drop_table("tag_categories")
    op.add_column("tags", sa.Column("description", sa.Text()))
    op.add_column("tags", sa.Column("parent_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_topics_parent_id_topics"),
        "tags",
        "tags",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_topics_parent_sort_order", "tags", ["parent_id", "sort_order"])
    op.execute("ALTER INDEX ix_tags_active_sort_order RENAME TO ix_topics_active_sort_order")
    op.execute("ALTER INDEX ix_event_tags_tag_event RENAME TO ix_event_topics_topic_event")
    rename_constraint("tags", "pk_tags", "pk_topics")
    rename_constraint("tags", "uq_tags_slug", "uq_topics_slug")
    rename_constraint("event_tags", "pk_event_tags", "pk_event_topics")
    rename_constraint(
        "event_tags", "fk_event_tags_event_id_events", "fk_event_topics_event_id_events"
    )
    rename_constraint("event_tags", "fk_event_tags_tag_id_tags", "fk_event_topics_topic_id_topics")
    op.alter_column("event_tags", "tag_id", new_column_name="topic_id")
    op.rename_table("tags", "topics")
    op.rename_table("event_tags", "event_topics")
