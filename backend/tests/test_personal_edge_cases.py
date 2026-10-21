import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_personal_scenarios import client, event, invite, pytestmark, user  # noqa: F401


def test_profile_rename_race_returns_conflict_instead_of_server_error() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            first, second = await user(http), await user(http)
            username = "same_" + uuid4().hex
            responses = await asyncio.gather(
                *[
                    http.patch(f"/api/users/{user_id}", json={"username": username})
                    for user_id in (first, second)
                ]
            )
            assert sorted(response.status_code for response in responses) == [200, 409]

    asyncio.run(scenario())


def test_deleted_events_disappear_from_personal_lists_and_invitations() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            owner, recipient = await user(http), await user(http)
            card = await event(http, owner)
            event_id = card["id"]
            assert (
                await http.put(f"/api/users/{recipient}/favorites/{event_id}")
            ).status_code == 200
            assert (
                await http.put(f"/api/users/{recipient}/dismissed/{event_id}")
            ).status_code == 200
            invitation_id = await invite(http, event_id, owner, recipient)
            assert (await http.delete(f"/api/events/{event_id}")).status_code == 422
            assert (
                await http.delete(f"/api/events/{event_id}?actor_id={recipient}")
            ).status_code == 403
            assert (
                await http.delete(f"/api/events/{event_id}?actor_id={owner}")
            ).status_code == 204
            for path in (
                f"/api/users/{owner}/events",
                f"/api/users/{recipient}/favorites",
                f"/api/users/{recipient}/dismissed",
                f"/api/users/{recipient}/invitations",
            ):
                assert (await http.get(path)).json() == []
            assert (
                await http.patch(
                    f"/api/invitations/{invitation_id}",
                    json={
                        "user_id": recipient,
                        "accept": True,
                    },
                )
            ).status_code == 409

    asyncio.run(scenario())


def test_already_going_invitee_does_not_consume_another_place() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            owner, recipient = await user(http), await user(http)
            card = await event(http, owner, capacity=1)
            assert (
                await http.post(
                    f"/api/events/{card['id']}/participants",
                    json={
                        "user_id": recipient,
                    },
                )
            ).status_code == 200
            invitation_id = await invite(http, card["id"], owner, recipient)
            response = await http.patch(
                f"/api/invitations/{invitation_id}",
                json={
                    "user_id": recipient,
                    "accept": True,
                },
            )
            assert response.status_code == 200, response.text
            assert (await http.get(f"/api/events/{card['id']}")).json()["participants_count"] == 1

    asyncio.run(scenario())


def test_invitation_validation_and_request_review_race() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            owner, recipient = await user(http), await user(http)
            card = await event(http, owner, join_policy="REQUEST")
            path = f"/api/events/{card['id']}/invitations"
            for body in (
                {"actor_id": owner, "invitee_id": owner},
                {
                    "actor_id": owner,
                    "invitee_id": recipient,
                    "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            ):
                assert (await http.post(path, json=body)).status_code == 422
            participation = f"/api/events/{card['id']}/participants"
            assert (await http.post(participation, json={"user_id": recipient})).status_code == 200
            responses = await asyncio.wait_for(
                asyncio.gather(
                    http.post(participation, json={"user_id": recipient}),
                    http.patch(
                        f"{participation}/{recipient}", json={"actor_id": owner, "accept": True}
                    ),
                ),
                timeout=10,
            )
            assert all(response.status_code == 200 for response in responses)
            assert (await http.get(f"/api/events/{card['id']}?viewer_id={recipient}")).json()[
                "personal_state"
            ]["participation_status"] == "GOING"

    asyncio.run(scenario())
