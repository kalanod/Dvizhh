"""Indexed generated geographic position for event discovery."""

import sqlalchemy as sa

from alembic import op
from dvizh_backend.database.geo import GeoPoint

revision = "20261117_discovery_geo"
down_revision = "20261114_admin_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.add_column(
        "locations",
        sa.Column(
            "position",
            GeoPoint(),
            sa.Computed(
                "CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL "
                "THEN ST_SetSRID(ST_MakePoint(longitude::double precision, "
                "latitude::double precision), 4326) ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_locations_position_gist", "locations", ["position"], postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_index("ix_locations_position_gist", table_name="locations")
    op.drop_column("locations", "position")
    # The shared PostGIS extension is deliberately retained.
