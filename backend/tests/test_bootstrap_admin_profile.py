"""Execute the seed against actual uniqueness and foreign key constraints."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa


@pytest.fixture
def seed(monkeypatch):
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/20261113_0005_bootstrap_admin_profile.py"
    )
    spec = spec_from_file_location("bootstrap_admin_profile", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    profiles = sa.Table(
        "profiles", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("bio", sa.Text()),
    )
    owned = sa.Table(
        "owned", metadata,
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(profiles.c.id), primary_key=True),
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        yield migration, connection, profiles, owned
    engine.dispose()


def test_bootstrap_creates_profile_with_auth_id_and_is_repeatable(seed):
    migration, connection, profiles, _ = seed
    migration.upgrade()
    migration.upgrade()
    profile, = connection.execute(sa.select(profiles)).mappings().all()
    assert profile["id"] == migration.ADMIN_ID
    assert profile["username"] == "admin"
    assert profile["display_name"] == "Администратор"


@pytest.mark.parametrize("fallback_taken", [False, True])
def test_username_collision_preserves_original_profile_and_references(seed, fallback_taken):
    migration, connection, profiles, owned = seed
    original_id = uuid4()
    original = {"id": original_id, "username": "admin", "display_name": "Old", "bio": "Keep"}
    connection.execute(profiles.insert().values(**original))
    connection.execute(owned.insert().values(owner_id=original_id))
    fallback = f"admin_{migration.ADMIN_ID.hex}"
    if fallback_taken:
        connection.execute(profiles.insert().values(
            id=uuid4(), username=fallback, display_name="Other",
        ))

    migration.upgrade()
    migration.upgrade()
    migration.downgrade()

    assert dict(connection.execute(
        sa.select(profiles).where(profiles.c.id == original_id)
    ).mappings().one()) == original
    assert connection.scalar(sa.select(owned.c.owner_id)) == original_id
    bootstrap = connection.execute(
        sa.select(profiles).where(profiles.c.id == migration.ADMIN_ID)
    ).mappings().one()
    assert bootstrap["username"] == fallback + ("_1" if fallback_taken else "")
    assert connection.scalar(sa.select(sa.func.count()).select_from(profiles)) == (
        3 if fallback_taken else 2
    )


def test_existing_bootstrap_profile_is_preserved_with_renamed_username(seed):
    migration, connection, profiles, _ = seed
    original = {
        "id": migration.ADMIN_ID, "username": "renamed_admin",
        "display_name": "Custom name", "bio": "Custom bio",
    }
    connection.execute(profiles.insert().values(**original))
    connection.execute(profiles.insert().values(id=uuid4(), username="admin", display_name="Other"))
    migration.upgrade()
    assert dict(connection.execute(
        sa.select(profiles).where(profiles.c.id == migration.ADMIN_ID)
    ).mappings().one()) == original
    assert connection.scalar(sa.select(sa.func.count()).select_from(profiles)) == 2
