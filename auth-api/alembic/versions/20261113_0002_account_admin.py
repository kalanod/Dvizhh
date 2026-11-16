"""Add explicitly granted administrator privileges."""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0002"
down_revision = "fb9928246bf3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("accounts", "is_admin")
