"""Store only the city in user profiles; event locations keep their coordinates."""

import sqlalchemy as sa

from alembic import op

revision = "20261118_profile_city"
down_revision = "20261117_discovery_geo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_profiles_latitude_range"), "profiles", type_="check")
    op.drop_constraint(op.f("ck_profiles_longitude_range"), "profiles", type_="check")
    op.drop_column("profiles", "latitude")
    op.drop_column("profiles", "longitude")


def downgrade() -> None:
    # Removed personal coordinates cannot be recovered; restored columns are empty.
    op.add_column("profiles", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("profiles", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint("latitude_range", "profiles", "latitude BETWEEN -90 AND 90")
    op.create_check_constraint("longitude_range", "profiles", "longitude BETWEEN -180 AND 180")
