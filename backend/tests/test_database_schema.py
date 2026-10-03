from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint

from dvizh_backend.database import models  # noqa: F401
from dvizh_backend.database.base import Base
from dvizh_backend.database.services.exceptions import InvalidStateTransitionError
from dvizh_backend.database.services.social import FriendshipService

EXPECTED_TABLES = {
    "event_dismissals",
    "event_favorites",
    "event_interactions",
    "event_invitations",
    "event_managers",
    "event_media",
    "event_occurrences",
    "event_participations",
    "event_stories",
    "event_topics",
    "events",
    "external_event_links",
    "external_sources",
    "friendships",
    "locations",
    "media_assets",
    "organization_members",
    "organizations",
    "participation_status_history",
    "profiles",
    "recurrence_rules",
    "story_items",
    "topics",
}


def test_all_domain_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_migration_snapshot_covers_every_model() -> None:
    sql_dir = Path(__file__).parents[1] / "alembic" / "versions" / "sql"
    upgrade_sql = (sql_dir / "20261003_0002_core_schema.up.sql").read_text(encoding="utf-8")
    downgrade_sql = (sql_dir / "20261003_0002_core_schema.down.sql").read_text(
        encoding="utf-8"
    )

    for table_name in EXPECTED_TABLES:
        assert f"CREATE TABLE {table_name} (" in upgrade_sql
        assert f"DROP TABLE {table_name};" in downgrade_sql


def test_critical_event_constraints_are_present() -> None:
    constraint_names = {
        constraint.name
        for constraint in Base.metadata.tables["events"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_events_location_matches_format",
        "ck_events_organizer_matches_origin",
        "ck_events_positive_capacity",
        "ck_events_price_fields_match_type",
    } <= constraint_names


def test_friendship_pair_is_canonical() -> None:
    first = UUID("00000000-0000-0000-0000-000000000002")
    second = UUID("00000000-0000-0000-0000-000000000001")

    assert FriendshipService._canonical_pair(first, second) == (second, first)
    with pytest.raises(InvalidStateTransitionError):
        FriendshipService._canonical_pair(first, first)
