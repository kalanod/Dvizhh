"""Use mandatory usernames and optional email addresses for account credentials."""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0004"
down_revision = "20261113_0003"
branch_labels = None
depends_on = None

ADMIN_ID = "d035b112-2cdf-5d23-9361-5db5dc3f162c"


def upgrade() -> None:
    op.add_column("accounts", sa.Column("username", sa.String(50)))
    op.alter_column("accounts", "email", existing_type=sa.String(254), nullable=True)
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE accounts SET username = CASE WHEN id = :admin_id THEN 'admin' "
            "ELSE 'user_' || replace(id::text, '-', '') END"
        ),
        {"admin_id": ADMIN_ID},
    )
    connection.execute(
        sa.text("UPDATE accounts SET email = NULL WHERE id = :admin_id AND email = 'admin'"),
        {"admin_id": ADMIN_ID},
    )
    connection.execute(
        sa.text(
            "WITH duplicates AS (SELECT id, row_number() OVER ("
            "PARTITION BY lower(btrim(email)) ORDER BY created_at, id) AS position "
            "FROM accounts WHERE email IS NOT NULL) "
            "UPDATE accounts SET email = NULL FROM duplicates "
            "WHERE accounts.id = duplicates.id AND duplicates.position > 1"
        )
    )
    connection.execute(sa.text("UPDATE accounts SET email = lower(btrim(email))"))
    op.alter_column("accounts", "username", nullable=False)
    op.create_unique_constraint("uq_accounts_username", "accounts", ["username"])
    op.create_check_constraint(
        "ck_accounts_username",
        "accounts",
        "username ~ '^[a-z0-9_]{3,50}$'",
    )
    op.create_check_constraint(
        "ck_accounts_email",
        "accounts",
        "email IS NULL OR email = lower(btrim(email))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_accounts_email", "accounts", type_="check")
    op.drop_constraint("ck_accounts_username", "accounts", type_="check")
    op.drop_constraint("uq_accounts_username", "accounts", type_="unique")
    op.execute(
        sa.text(
            "UPDATE accounts SET email = CASE "
            f"WHEN id = '{ADMIN_ID}' THEN 'admin' "
            "ELSE 'user_' || replace(id::text, '-', '') || '@migration.invalid' END "
            "WHERE email IS NULL"
        )
    )
    op.alter_column("accounts", "email", existing_type=sa.String(254), nullable=False)
    op.drop_column("accounts", "username")
