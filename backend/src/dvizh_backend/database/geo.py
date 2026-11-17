"""PostGIS types without an additional ORM dependency."""

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class GeoPoint(UserDefinedType):
    cache_ok = True

    def __init__(self, *args, **kwargs):
        pass

    def get_col_spec(self, **kw):
        return "geometry(Point,4326)"


class GeographyPoint(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return "geography(Point,4326)"


# SQLAlchemy reflection must recognize PostGIS columns during Alembic check.
ischema_names.setdefault("geometry", GeoPoint)
