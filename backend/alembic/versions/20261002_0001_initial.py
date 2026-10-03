"""Initialize migration history without domain tables.

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

revision: str = "20261002_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
