import asyncio
from uuid import UUID

from sqlalchemy import func, select
from test_media_lifecycle import client, event, pytestmark, upload, user  # noqa: F401

from dvizh_backend.database.models import EventDismissal, EventFavorite, EventInteraction


def test_cover_personal_lists_invitations_and_notifications_work_together() -> None:
    async def scenario() -> None:
        async with client() as (http, _, _storage):
            owner, participant, invitee = [await user(http) for _ in range(3)]
            card = await event(http, owner, draft=True)
            event_id = card["id"]
            asset = await upload(http, owner)
            cover = await http.put(
                f"/api/events/{event_id}/cover?actor_id={owner}",
                json={"media_id": asset["id"]},
            )
            assert cover.status_code == 200, cover.text
            drafts = (await http.get(f"/api/users/{owner}/drafts")).json()
            assert drafts[0]["cover_media_id"] == asset["id"]
            assert drafts[0]["personal_state"]["is_favorite"] is False
            assert (
                await http.post(f"/api/events/{event_id}/publish", json={"actor_id": owner})
            ).status_code == 200
            assert (
                await http.put(f"/api/users/{participant}/favorites/{event_id}")
            ).json()["cover_media_id"] == asset["id"]
            assert (
                await http.post(
                    f"/api/events/{event_id}/participants", json={"user_id": participant}
                )
            ).status_code == 200
            assert (
                await http.post(
                    f"/api/events/{event_id}/invitations",
                    json={"actor_id": owner, "invitee_id": invitee},
                )
            ).status_code == 200

            for path in (
                f"/api/users/{participant}/favorites",
                f"/api/users/{participant}/events?kind=participating",
                f"/api/users/{participant}/calendar",
                f"/api/events?viewer_id={participant}&limit=100",
            ):
                cards = (await http.get(path)).json()
                personal = next(item for item in cards if item["id"] == event_id)
                assert personal["cover_media_id"] == asset["id"]
                assert personal["cover_url"] == asset["content_url"]
                assert personal["personal_state"] == {
                    "is_favorite": True,
                    "is_dismissed": False,
                    "participation_status": "GOING",
                }
            invitation = (await http.get(f"/api/users/{invitee}/invitations")).json()[0]
            assert invitation["event"]["cover_media_id"] == asset["id"]
            assert invitation["event"]["personal_state"]["is_favorite"] is False

            replacement = await upload(http, owner)
            assert (
                await http.put(
                    f"/api/events/{event_id}/cover?actor_id={owner}",
                    json={"media_id": replacement["id"]},
                )
            ).status_code == 200
            for recipient in (participant, invitee):
                notices = (await http.get(f"/api/users/{recipient}/notifications")).json()
                assert len(notices) == 1
                assert notices[0]["payload"]["changed_fields"] == ["cover_media_id"]

            assert (
                await http.post(f"/api/events/{event_id}/cancel", json={"actor_id": owner})
            ).status_code == 200
            assert (await http.get(f"/api/users/{participant}/calendar")).json() == []
            assert (await http.get(f"/api/users/{invitee}/invitations")).json() == []
            for recipient in (participant, invitee):
                notices = (await http.get(f"/api/users/{recipient}/notifications")).json()
                assert len(notices) == 2
                assert notices[0]["kind"] == "EVENT_CANCELLED"

    asyncio.run(scenario())


def test_draft_cannot_leak_through_favorites_or_dismissals() -> None:
    async def scenario() -> None:
        async with client() as (http, database, _storage):
            owner, stranger = await user(http), await user(http)
            card = await event(http, owner, draft=True)
            for kind in ("favorites", "dismissed"):
                path = f"/api/users/{stranger}/{kind}"
                assert (await http.put(f"{path}/{card['id']}")).status_code == 403
                assert (await http.get(path)).json() == []
            async with database.session() as session:
                for model in (EventFavorite, EventDismissal, EventInteraction):
                    count = await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.user_id == UUID(stranger))
                    )
                    assert count == 0

    asyncio.run(scenario())
