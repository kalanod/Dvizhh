"""HTTP scenarios against a migrated, disposable PostgreSQL test database."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url

from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.database.dependencies import get_database_service
from dvizh_backend.database.models import (
    EventInteraction,
    EventInvitation,
    EventManager,
    EventParticipation,
    ParticipationStatusHistory,
)
from dvizh_backend.database.models.enums import EventManagerRole, InteractionType
from dvizh_backend.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires isolated PostgreSQL")


@asynccontextmanager
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, DatabaseService]]:
    assert TEST_DATABASE_URL is not None
    assert make_url(TEST_DATABASE_URL).database == "dvizh_scenarios_test", (
        "Integration tests require the disposable database dvizh_scenarios_test"
    )
    database = DatabaseService(TEST_DATABASE_URL)
    app.dependency_overrides[get_database_service] = lambda: database
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            yield http, database
    finally:
        app.dependency_overrides.pop(get_database_service, None)
        await database.dispose()


async def user(http: httpx.AsyncClient) -> str:
    response = await http.post(
        "/api/users",
        json={
            "username": "u_" + uuid4().hex,
            "display_name": "Test user",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def event(http: httpx.AsyncClient, owner: str, **fields: object) -> dict:
    response = await http.post(
        "/api/events",
        json={
            "organizer_id": owner,
            "title": "Test " + uuid4().hex,
            "starts_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "format": "ONLINE",
            "online_url": "https://example.com/live",
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def invite(http: httpx.AsyncClient, event_id: str, owner: str, recipient: str) -> str:
    response = await http.post(
        f"/api/events/{event_id}/invitations",
        json={
            "actor_id": owner,
            "invitee_id": recipient,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_profile_patch_and_friend_request_inboxes() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            first, second = await user(http), await user(http)
            response = await http.patch(
                f"/api/users/{first}",
                json={
                    "display_name": "Updated",
                    "bio": None,
                    "latitude": "55.75",
                    "longitude": "37.61",
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["display_name"] == "Updated"
            assert response.json()["latitude"] == "55.750000"
            for patch in ({}, {"display_name": None}, {"latitude": "1"}, {"unknown": True}):
                assert (await http.patch(f"/api/users/{first}", json=patch)).status_code == 422
            name = (await http.get(f"/api/users/{second}")).json()["username"]
            assert (
                await http.patch(f"/api/users/{first}", json={"username": name})
            ).status_code == 409
            assert (await http.put(f"/api/users/{first}/friends/{second}")).status_code == 200
            inbox = (await http.get(f"/api/users/{second}/friends/requests")).json()
            assert inbox[0]["user"]["id"] == first
            assert (await http.get(f"/api/users/{first}/friends/requests")).json() == []
            sent = (
                await http.get(f"/api/users/{first}/friends/requests?direction=outgoing")
            ).json()
            assert sent[0]["user"]["id"] == second
            assert (
                await http.patch(
                    f"/api/users/{second}/friends/{first}",
                    json={
                        "accept": True,
                    },
                )
            ).status_code == 200
            assert (await http.get(f"/api/users/{second}/friends/requests")).json() == []

    asyncio.run(scenario())


def test_favorites_dismissal_personal_cards_and_retry_logs() -> None:
    async def scenario() -> None:
        async with client() as (http, database):
            owner, viewer, other = await user(http), await user(http), await user(http)
            card = await event(http, owner)
            event_id = card["id"]
            favorite = f"/api/users/{viewer}/favorites/{event_id}"
            responses = await asyncio.gather(http.put(favorite), http.put(favorite))
            assert all(response.status_code == 200 for response in responses)
            assert responses[0].json()["personal_state"]["is_favorite"]
            assert event_id in {
                item["id"] for item in (await http.get(f"/api/users/{viewer}/favorites")).json()
            }
            assert (await http.get(f"/api/users/{other}/favorites")).json() == []
            dismissal = f"/api/users/{viewer}/dismissed/{event_id}"
            for _ in range(2):
                assert (await http.put(dismissal)).status_code == 200
            assert event_id not in {
                item["id"]
                for item in (await http.get(f"/api/events?viewer_id={viewer}&limit=100")).json()
            }
            state = (await http.get(f"/api/events/{event_id}?viewer_id={viewer}")).json()[
                "personal_state"
            ]
            assert state == {
                "is_favorite": True,
                "is_dismissed": True,
                "participation_status": None,
            }
            assert (await http.get(f"/api/events/{event_id}")).json()["personal_state"] is None
            assert (await http.delete(dismissal)).json()["personal_state"]["is_dismissed"] is False
            assert event_id in {
                item["id"]
                for item in (await http.get(f"/api/events?viewer_id={viewer}&limit=100")).json()
            }
            for _ in range(2):
                assert (await http.delete(favorite)).status_code == 200
            async with database.session() as session:
                rows = (
                    await session.execute(
                        select(EventInteraction.type, func.count())
                        .where(EventInteraction.user_id == viewer)
                        .group_by(EventInteraction.type)
                    )
                ).all()
                assert dict(rows) == {
                    InteractionType.FAVORITE_ADD: 1,
                    InteractionType.FAVORITE_REMOVE: 1,
                    InteractionType.NOT_INTERESTED: 1,
                }
            assert (await http.put(f"/api/users/{viewer}/favorites/{uuid4()}")).status_code == 404

    asyncio.run(scenario())


def test_my_events_and_participation_states() -> None:
    async def scenario() -> None:
        async with client() as (http, _):
            owner, participant = await user(http), await user(http)
            card = await event(http, owner, join_policy="REQUEST")
            event_id = card["id"]
            assert (await http.get(f"/api/users/{participant}/events")).json() == []
            organized = (await http.get(f"/api/users/{owner}/events")).json()
            assert [item["id"] for item in organized] == [event_id]
            assert (
                await http.post(
                    f"/api/events/{event_id}/participants",
                    json={
                        "user_id": participant,
                    },
                )
            ).json()["status"] == "REQUESTED"
            requests = (await http.get(f"/api/users/{participant}/events?kind=requested")).json()
            assert requests[0]["personal_state"]["participation_status"] == "REQUESTED"
            assert (
                await http.patch(
                    f"/api/events/{event_id}/participants/{participant}",
                    json={
                        "actor_id": owner,
                        "accept": False,
                        "reason": "Full group",
                    },
                )
            ).json()["status"] == "REJECTED"
            assert (await http.get(f"/api/events/{event_id}?viewer_id={participant}")).json()[
                "personal_state"
            ]["participation_status"] == "REJECTED"
            assert (await http.get(f"/api/users/{participant}/events?kind=requested")).json() == []
            assert (
                await http.post(
                    f"/api/events/{event_id}/participants",
                    json={
                        "user_id": participant,
                    },
                )
            ).status_code == 409
            open_card = await event(http, owner)
            assert (
                await http.post(
                    f"/api/events/{open_card['id']}/participants",
                    json={
                        "user_id": participant,
                    },
                )
            ).json()["status"] == "GOING"
            going = (await http.get(f"/api/users/{participant}/events?kind=participating")).json()
            assert going[0]["personal_state"]["participation_status"] == "GOING"
            assert (
                await http.get(f"/api/users/{participant}/events?kind=wrong")
            ).status_code == 422
            assert (
                await http.get(f"/api/users/{participant}/favorites?limit=101")
            ).status_code == 422

    asyncio.run(scenario())


def test_invitation_permission_capacity_and_idempotent_acceptance() -> None:
    async def scenario() -> None:
        async with client() as (http, database):
            owner, first, second, stranger = [await user(http) for _ in range(4)]
            card = await event(http, owner, join_policy="INVITE_ONLY", capacity=1)
            event_id = card["id"]
            assert (
                await http.post(
                    f"/api/events/{event_id}/invitations",
                    json={
                        "actor_id": stranger,
                        "invitee_id": first,
                    },
                )
            ).status_code == 403
            invitations = [
                await invite(http, event_id, owner, recipient) for recipient in (first, second)
            ]
            assert await invite(http, event_id, owner, first) == invitations[0]
            inbox = (await http.get(f"/api/users/{first}/invitations")).json()
            assert inbox[0]["event"]["id"] == event_id
            assert inbox[0]["invitation"]["id"] == invitations[0]
            assert (
                await http.patch(
                    f"/api/invitations/{invitations[0]}",
                    json={
                        "user_id": stranger,
                        "accept": True,
                    },
                )
            ).status_code == 403
            responses = await asyncio.gather(
                *[
                    http.patch(
                        f"/api/invitations/{invitation_id}",
                        json={
                            "user_id": recipient,
                            "accept": True,
                        },
                    )
                    for invitation_id, recipient in zip(invitations, (first, second), strict=True)
                ]
            )
            assert sorted(response.status_code for response in responses) == [200, 409]
            winner = 0 if responses[0].status_code == 200 else 1
            for _ in range(2):
                retry = await http.patch(
                    f"/api/invitations/{invitations[winner]}",
                    json={
                        "user_id": (first, second)[winner],
                        "accept": True,
                    },
                )
                assert retry.status_code == 200, retry.text
            async with database.session() as session:
                participations = (
                    await session.scalars(
                        select(EventParticipation).where(
                            EventParticipation.occurrence_id == card["occurrence_id"]
                        )
                    )
                ).all()
                assert len(participations) == 1
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ParticipationStatusHistory)
                        .where(ParticipationStatusHistory.participation_id == participations[0].id)
                    )
                ) == 1

    asyncio.run(scenario())


def test_expired_declined_revoked_and_manager_invitations() -> None:
    async def scenario() -> None:
        async with client() as (http, database):
            owner, recipient, manager = [await user(http) for _ in range(3)]
            card = await event(http, owner, join_policy="INVITE_ONLY")
            async with database.session() as session:
                session.add(
                    EventManager(
                        event_id=card["id"], user_id=manager, role=EventManagerRole.MANAGER
                    )
                )
            invitation_id = await invite(http, card["id"], manager, recipient)
            for _ in range(2):
                assert (
                    await http.patch(
                        f"/api/invitations/{invitation_id}",
                        json={
                            "user_id": recipient,
                            "accept": False,
                        },
                    )
                ).json()["status"] == "DECLINED"
            assert await invite(http, card["id"], owner, recipient) == invitation_id
            async with database.session() as session:
                await session.execute(
                    update(EventInvitation)
                    .where(EventInvitation.id == invitation_id)
                    .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
                )
            assert (await http.get(f"/api/users/{recipient}/invitations")).json() == []
            assert (
                await http.patch(
                    f"/api/invitations/{invitation_id}",
                    json={
                        "user_id": recipient,
                        "accept": True,
                    },
                )
            ).status_code == 409
            assert await invite(http, card["id"], owner, recipient) == invitation_id
            assert (
                await http.delete(f"/api/invitations/{invitation_id}?actor_id={recipient}")
            ).status_code == 403
            for _ in range(2):
                assert (
                    await http.delete(f"/api/invitations/{invitation_id}?actor_id={manager}")
                ).json()["status"] == "REVOKED"
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
