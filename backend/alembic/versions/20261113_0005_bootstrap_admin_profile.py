"""Create the profile for the auth service's initial administrator."""

from alembic import op

revision = "20261113_admin_profile"
down_revision = "20261111_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO profiles (id, username, display_name) "
        "VALUES ('d035b112-2cdf-5d23-9361-5db5dc3f162c', 'admin', 'Администратор') "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    # The profile can own events and other data; reverting the seed must not delete it.
    pass
