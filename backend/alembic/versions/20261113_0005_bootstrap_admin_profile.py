"""Create the profile for the auth service's initial administrator."""

from itertools import count
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from alembic import op

revision = "20261113_admin_profile"
down_revision = "20261111_0004"
branch_labels = None
depends_on = None

ADMIN_ID = UUID("d035b112-2cdf-5d23-9361-5db5dc3f162c")


def upgrade() -> None:
    profiles = sa.table(
        "profiles",
        sa.column("id", sa.Uuid()),
        sa.column("username", sa.String(50)),
        sa.column("display_name", sa.String(120)),
    )
    connection = op.get_bind()
    existing = sa.select(profiles.c.id).where(profiles.c.id == ADMIN_ID)
    if connection.scalar(existing) is not None:
        return

    # The username alone does not prove ownership of an existing profile. Keep
    # its ID and domain data; auth identifies the bootstrap account by ADMIN_ID.
    for suffix in count():
        username = "admin" if suffix == 0 else f"admin_{ADMIN_ID.hex}"
        if suffix > 1:
            username += f"_{suffix - 1}"
        created_id = connection.scalar(
            insert(profiles)
            .values(id=ADMIN_ID, username=username, display_name="Администратор")
            .on_conflict_do_nothing()
            .returning(profiles.c.id)
        )
        # Another migration runner may have inserted the same ID in parallel.
        if created_id is not None or connection.scalar(existing) is not None:
            return


def downgrade() -> None:
    # The profile can own events and other data; reverting the seed must not delete it.
    pass
