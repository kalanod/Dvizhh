"""Bridge legacy administrator flags and existing role-based deployments."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from alembic import op

revision = "20261114_0002_roles"
down_revision = "20261113_0002"
branch_labels = None
depends_on = None

USER_ROLE_ID = "741abca2-761f-5f9c-b35d-8b1efa9ef675"
ADMIN_ROLE_ID = "76524bee-a7f4-51b5-8b58-bb300ee09f3e"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "roles" not in inspector.get_table_names():
        op.create_table(
            "roles",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(20), unique=True, nullable=False),
            sa.CheckConstraint("name IN ('user', 'admin')", name="ck_roles_name"),
        )
    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("name", sa.String(20)))
    connection.execute(
        insert(roles)
        .values(
            [
                {"id": UUID(USER_ROLE_ID), "name": "user"},
                {"id": UUID(ADMIN_ROLE_ID), "name": "admin"},
            ]
        )
        .on_conflict_do_nothing()
    )
    columns = {column["name"] for column in inspector.get_columns("accounts")}
    if "role_id" not in columns:
        op.add_column(
            "accounts",
            sa.Column(
                "role_id",
                sa.Uuid(),
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
    if "is_admin" in columns:
        connection.execute(
            sa.text("UPDATE accounts SET role_id = :admin_role WHERE is_admin IS TRUE"),
            {"admin_role": ADMIN_ROLE_ID},
        )
        op.drop_column("accounts", "is_admin")
    connection.execute(
        sa.text("UPDATE accounts SET role_id = :role WHERE role_id IS NULL"), {"role": USER_ROLE_ID}
    )
    op.alter_column(
        "accounts",
        "role_id",
        nullable=False,
        server_default=sa.text(f"'{USER_ROLE_ID}'"),
    )


def downgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text(f"UPDATE accounts SET is_admin = (role_id = '{ADMIN_ROLE_ID}')"))
    op.drop_constraint("fk_accounts_role_id_roles", "accounts", type_="foreignkey")
    op.drop_column("accounts", "role_id")
    op.drop_table("roles")
