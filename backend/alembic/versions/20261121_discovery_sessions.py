import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261121_discovery_sessions"
down_revision = "20261120_recsys_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_discovery_sessions_expires_at"), "discovery_sessions", ["expires_at"])
    op.create_table(
        "discovery_pages",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("page", sa.Integer(), primary_key=True),
        sa.Column("items", JSONB(), nullable=False),
        sa.Column("request_id", sa.Uuid()),
        sa.Column("next_page_token", sa.Text()),
        sa.Column("fallback_after", JSONB(none_as_null=True)),
    )


def downgrade() -> None:
    op.drop_table("discovery_pages")
    op.drop_table("discovery_sessions")
