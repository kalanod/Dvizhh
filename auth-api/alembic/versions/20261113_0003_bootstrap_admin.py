"""Create the initial system administrator without resetting existing credentials."""

from uuid import UUID

import sqlalchemy as sa
from pwdlib import PasswordHash
from sqlalchemy.dialects.postgresql import insert

from alembic import op

revision = "20261113_0003"
down_revision = "20261113_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    accounts = sa.table(
        "accounts",
        sa.column("id", sa.Uuid()),
        sa.column("email", sa.String(254)),
        sa.column("password_hash", sa.Text()),
        sa.column("role_id", sa.Uuid()),
    )
    op.execute(
        insert(accounts)
        .values(
            id=UUID("d035b112-2cdf-5d23-9361-5db5dc3f162c"),
            email="admin",
            password_hash=PasswordHash.recommended().hash("admin"),
            role_id=UUID("76524bee-a7f4-51b5-8b58-bb300ee09f3e"),
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    """Keep the account and its data; rolling back a seed must not remove a user."""
