from datetime import date

import pytest
from pydantic import ValidationError

from dvizh_backend.main import app
from dvizh_backend.schemas import EventUpdate


def test_openapi_lists_endpoints() -> None:
    paths = app.openapi()["paths"]

    assert "/api/events" in paths
    assert "/api/events/{event_id}/participants" in paths
    assert "/api/users/{user_id}/friends/{friend_id}" in paths
    assert "/api/users/{user_id}/calendar" in paths


def test_event_end_date_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventUpdate(title="Поход", start_date=date(2026, 10, 3), end_date=date(2026, 10, 2))


def test_event_columns_are_normalized() -> None:
    event = EventUpdate(
        title="  Настолки ", start_date=date(2026, 10, 3), tags=["Игры", "игры ", ""], price=0
    )

    columns = event.to_columns()

    assert columns["title"] == "Настолки"
    assert columns["tags"] == ["игры"]
    assert columns["price"] is None
