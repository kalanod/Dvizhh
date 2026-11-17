"""Remove invitation expiry while keeping already expired invitations closed."""

import sqlalchemy as sa

from alembic import op

revision = "20261119_invite_no_expiry"
down_revision = "20261118_profile_city"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE event_invitations
        SET status = 'EXPIRED', responded_at = COALESCE(responded_at, now())
        WHERE status = 'PENDING' AND expires_at IS NOT NULL AND expires_at <= now()
    """)
    op.drop_column("event_invitations", "expires_at")


def downgrade() -> None:
    op.add_column("event_invitations", sa.Column(
        "expires_at", sa.DateTime(timezone=True), nullable=True,
    ))
