"""Allow event locations specified by address without coordinates."""

import sqlalchemy as sa

from alembic import op

revision = "20261111_0004"
down_revision = "20261014_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("latitude", "longitude"):
        op.alter_column("locations", column, existing_type=sa.Numeric(9, 6), nullable=True)


def downgrade() -> None:
    for column in ("latitude", "longitude"):
        op.alter_column("locations", column, existing_type=sa.Numeric(9, 6), nullable=False)
