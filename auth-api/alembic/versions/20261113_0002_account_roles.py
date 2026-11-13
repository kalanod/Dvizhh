"""Add user and administrator account roles."""

from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision = "20261113_0002"
down_revision = "fb9928246bf3"
branch_labels = None
depends_on = None

USER_ROLE_ID = "741abca2-761f-5f9c-b35d-8b1efa9ef675"
ADMIN_ROLE_ID = "76524bee-a7f4-51b5-8b58-bb300ee09f3e"


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(20), unique=True, nullable=False),
        sa.CheckConstraint("name IN ('user', 'admin')", name="ck_roles_name"),
    )
    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("name", sa.String(20)))
    op.bulk_insert(
        roles,
        [
            {"id": UUID(USER_ROLE_ID), "name": "user"},
            {"id": UUID(ADMIN_ROLE_ID), "name": "admin"},
        ],
    )
    op.add_column(
        "accounts",
        sa.Column(
            "role_id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text(f"'{USER_ROLE_ID}'"),
        ),
    )
    op.create_foreign_key(
        "fk_accounts_role_id_roles",
        "accounts",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_accounts_role_id_roles", "accounts", type_="foreignkey")
    op.drop_column("accounts", "role_id")
    op.drop_table("roles")
