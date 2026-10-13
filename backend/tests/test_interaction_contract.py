import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from dvizh_backend.database.models.enums import InteractionType
from dvizh_backend.dto.interaction import (
    InteractionBatchDTO,
    InteractionBatchResponseDTO,
    InteractionDTO,
)

INTERACTION_ID = "00000000-0000-0000-0000-000000000001"
ITEM_ID = "00000000-0000-0000-0000-000000000002"
SESSION_ID = "00000000-0000-0000-0000-000000000003"
REQUEST_ID = "00000000-0000-0000-0000-000000000004"


def interaction_payload(**changes: object) -> dict[str, object]:
    return {
        "interaction_id": INTERACTION_ID,
        "item_id": ITEM_ID,
        "event_type": "OPEN",
        "timestamp": "2026-10-07T12:30:00+03:00",
        **changes,
    }


def test_batch_accepts_decoded_http_json_and_preserves_origin() -> None:
    payload = {
        "interactions": [
            interaction_payload(session_id=SESSION_ID, request_id=REQUEST_ID),
            interaction_payload(
                interaction_id="00000000-0000-0000-0000-000000000005",
                event_type="IMPRESSION",
                session_id=SESSION_ID,
                request_id="00000000-0000-0000-0000-000000000006",
            ),
            interaction_payload(
                interaction_id="00000000-0000-0000-0000-000000000007",
                session_id=None,
                request_id=None,
            ),
        ]
    }

    batch = InteractionBatchDTO.model_validate(json.loads(json.dumps(payload)))

    assert batch.interactions[0].interaction_id == UUID(INTERACTION_ID)
    assert batch.interactions[0].session_id == UUID(SESSION_ID)
    assert batch.interactions[0].request_id == UUID(REQUEST_ID)
    assert batch.interactions[1].request_id != batch.interactions[0].request_id
    assert batch.interactions[2].session_id is None
    assert batch.interactions[2].request_id is None
    assert batch.interactions[0].timestamp.isoformat() == "2026-10-07T12:30:00+03:00"
    assert InteractionBatchDTO.model_validate_json(batch.model_dump_json()) == batch


@pytest.mark.parametrize("event_type", ["IMPRESSION", "OPEN", "JOIN_CLICK", "EXTERNAL_LINK_CLICK"])
def test_client_event_types_are_accepted(event_type: str) -> None:
    interaction = InteractionDTO.model_validate(interaction_payload(event_type=event_type))

    assert interaction.event_type == event_type


@pytest.mark.parametrize(
    "event_type",
    [
        member.value
        for member in InteractionType
        if member.value not in {"IMPRESSION", "OPEN", "JOIN_CLICK", "EXTERNAL_LINK_CLICK"}
    ]
    + ["PARTICIPATION_CONFIRMED", "UNKNOWN"],
)
def test_client_cannot_report_backend_actions(event_type: str) -> None:
    with pytest.raises(ValidationError):
        InteractionDTO.model_validate(interaction_payload(event_type=event_type))


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp": "2026-10-07T12:30:00"},
        {"timestamp": "invalid"},
        {"interaction_id": "invalid"},
        {"item_id": "invalid"},
        {"session_id": SESSION_ID},
        {"request_id": REQUEST_ID},
        {"session_id": None, "request_id": REQUEST_ID},
        {"session_id": "invalid", "request_id": REQUEST_ID},
        {"session_id": SESSION_ID, "request_id": "invalid"},
        {"user_id": ITEM_ID},
        {"received_at": "2026-10-07T12:31:00Z"},
        {"metadata": {}},
    ],
)
def test_invalid_interaction_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InteractionDTO.model_validate(interaction_payload(**changes))


@pytest.mark.parametrize(
    "payload",
    [
        {"interactions": []},
        {"interactions": [interaction_payload()], "user_id": ITEM_ID},
        {"interactions": [interaction_payload(), interaction_payload(event_type="JOIN_CLICK")]},
    ],
)
def test_invalid_batch_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InteractionBatchDTO.model_validate(payload)


def test_identical_duplicate_ids_are_allowed_in_a_batch() -> None:
    batch = InteractionBatchDTO.model_validate(
        {
            "interactions": [
                interaction_payload(),
                interaction_payload(timestamp="2026-10-07T09:30:00Z"),
            ]
        }
    )

    assert batch.interactions[0] == batch.interactions[1]


def test_response_serializes_ids_as_json_strings() -> None:
    response = InteractionBatchResponseDTO(accepted_interaction_ids=[UUID(INTERACTION_ID)])

    assert json.loads(response.model_dump_json()) == {"accepted_interaction_ids": [INTERACTION_ID]}
