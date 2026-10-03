"""Create the core Dvizh domain schema.

Revision ID: 20261003_0002
Revises: 20261002_0001
Create Date: 2026-10-03
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "20261003_0002"
down_revision: str | None = "20261002_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_snapshot(filename: str) -> None:
    script_path = Path(__file__).with_name("sql") / filename
    script = script_path.read_text(encoding="utf-8")
    for statement in script.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def upgrade() -> None:
    _execute_snapshot("20261003_0002_core_schema.up.sql")


def downgrade() -> None:
    _execute_snapshot("20261003_0002_core_schema.down.sql")
