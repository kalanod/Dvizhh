import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from integration_auth import account_headers
from sqlalchemy import select, text
from test_personal_scenarios import client, event, pytestmark, user  # noqa: F401

from dvizh_backend.database.models import (
    Event,
    EventInteraction,
    EventOccurrence,
    EventParticipation,
)
from dvizh_backend.database.models.enums import (
    EventVisibility,
    InteractionType,
    ParticipationStatus,
)


def test_concurrent_delivery_acknowledges_retry_and_rolls_back_conflicting_batch() -> None:
    async def scenario() -> None:
        async with client() as (http, database):
            owner, viewer = await user(http), await user(http)
            item = await event(http, owner)
            identifier = uuid4()
            other = UUID(int=identifier.int - 1)
            timestamp = datetime.now(UTC)
            action = {
                "item_id": item["id"],
                "event_type": "OPEN",
                "interaction_id": str(identifier),
                "timestamp": timestamp.isoformat(),
            }

            async def deliver(*actions):
                return await http.post(
                    "/api/interactions",
                    json={"interactions": actions},
                    headers=account_headers(viewer),
                )

            async with asyncio.TaskGroup() as deliveries, database.session() as first_delivery:
                first_delivery.add(
                    EventInteraction(
                        interaction_id=identifier,
                        user_id=UUID(viewer),
                        event_id=UUID(item["id"]),
                        type=InteractionType.OPEN,
                        occurred_at=timestamp,
                    )
                )
                await first_delivery.flush()
                blocker = await first_delivery.scalar(text("SELECT pg_backend_pid()"))
                retry = deliveries.create_task(deliver(action))
                conflict = deliveries.create_task(
                    deliver(
                        {**action, "interaction_id": str(other)},
                        {**action, "event_type": "IMPRESSION"},
                    )
                )
                async with database.session() as observer, asyncio.timeout(5):
                    blocked = text("""
                        SELECT count(*) FROM pg_stat_activity
                        WHERE :blocker = ANY(pg_blocking_pids(pid))
                    """)
                    while await observer.scalar(blocked, {"blocker": blocker}) != 2:
                        await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                        await asyncio.sleep(0.01)

            assert retry.result().status_code == 200, retry.result().text
            assert retry.result().json() == {"accepted_interaction_ids": [str(identifier)]}
            assert conflict.result().status_code == 409, conflict.result().text
            async with database.session() as session:
                records = (
                    await session.scalars(
                        select(EventInteraction).where(
                            EventInteraction.interaction_id.in_([identifier, other]),
                        )
                    )
                ).all()
            assert [(record.interaction_id, record.type) for record in records] == [
                (identifier, InteractionType.OPEN),
            ]

    asyncio.run(scenario())


def test_selected_occurrence_keeps_click_origin_through_approval_and_late_retry() -> None:
    async def scenario() -> None:
        async with client() as (http, database):
            owner, participant = await user(http), await user(http)
            card = await event(http, owner, join_policy="REQUEST")
            item_id = card["id"]
            selected_id = uuid4()
            starts_at = datetime.fromisoformat(card["starts_at"]) + timedelta(days=2)
            async with database.session() as session:
                session.add(
                    EventOccurrence(
                        id=selected_id,
                        event_id=UUID(item_id),
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=2),
                        timezone="UTC",
                        status="SCHEDULED",
                    )
                )

            path = f"/api/events/{item_id}/participants"
            detail = f"/api/events/{item_id}"
            selected = {"occurrence_id": str(selected_id)}
            click = {
                "interaction_id": str(uuid4()),
                "item_id": item_id,
                "event_type": "JOIN_CLICK",
                "timestamp": datetime.now(UTC).isoformat(),
                "session_id": str(uuid4()),
                "request_id": str(uuid4()),
            }
            body = {"user_id": participant, "interaction": click}
            view = text("""
                SELECT occurrence_id, origin_interaction_id
                FROM public.recsys_confirmed_registrations
                WHERE user_id = :user_id AND item_id = :item_id
            """)
            keys = {"user_id": UUID(participant), "item_id": UUID(item_id)}

            assert (await http.get(f"/api/events/{item_id}", params=selected)).json()[
                "occurrence_id"
            ] == str(selected_id)
            reported = await http.post(
                "/api/interactions",
                json={"interactions": [click]},
                headers=account_headers(participant),
            )
            assert reported.status_code == 200, reported.text
            impersonated = await http.post(
                path,
                params=selected,
                json=body,
                headers=account_headers(owner),
            )
            assert impersonated.status_code == 403, impersonated.text
            legacy_headers = {"Cookie": account_headers(participant)["Cookie"]}
            cross_origin = await http.post(
                path,
                params=selected,
                json=body,
                headers={**legacy_headers, "Origin": "http://another-origin.example"},
            )
            assert cross_origin.status_code == 403, cross_origin.text
            request = await http.post(
                path,
                params=selected,
                json=body,
                headers={**legacy_headers, "Origin": "http://test"},
            )
            assert request.status_code == 200, request.text
            assert request.json()["status"] == "REQUESTED"
            assert (await http.get(path)).json() == []
            async with database.session() as session:
                assert (await session.execute(view, keys)).all() == []

            approved = await http.patch(
                f"{path}/{participant}",
                params=selected,
                json={"actor_id": owner, "accept": True},
                headers=account_headers(owner),
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "GOING"
            cancelled = await http.delete(
                f"{path}/{participant}",
                params=selected,
                headers=account_headers(participant),
            )
            assert cancelled.status_code == 204, cancelled.text
            replay = await http.post(
                path,
                params=selected,
                json=body,
                headers=account_headers(participant),
            )
            assert replay.status_code == 200, replay.text
            assert replay.json()["status"] == "CANCELLED"

            pending_click = {**click, "interaction_id": str(uuid4())}
            reported = await http.post(
                "/api/interactions",
                json={"interactions": [pending_click]},
                headers=account_headers(participant),
            )
            assert reported.status_code == 200, reported.text
            async with database.session() as session:
                item = await session.get(Event, UUID(item_id))
                item.visibility = EventVisibility.PRIVATE

            for read_path in (detail, path):
                private = await http.get(read_path, params=selected)
                assert private.status_code == 404, private.text
            spoofed_detail = await http.get(
                detail,
                params={**selected, "viewer_id": owner},
                headers=legacy_headers,
            )
            assert spoofed_detail.status_code == 403, spoofed_detail.text
            owner_detail = await http.get(detail, params=selected, headers=account_headers(owner))
            assert owner_detail.status_code == 200, owner_detail.text
            blocked_join = await http.post(
                path,
                params=selected,
                json={"user_id": participant, "interaction": pending_click},
                headers=account_headers(participant),
            )
            assert blocked_join.status_code == 403, blocked_join.text
            async with database.session() as session:
                registrations = (await session.execute(view, keys)).all()
                participation = await session.scalar(
                    select(EventParticipation).where(
                        EventParticipation.occurrence_id == selected_id,
                        EventParticipation.user_id == UUID(participant),
                    )
                )
                assert participation.status == ParticipationStatus.CANCELLED
            assert registrations == [(selected_id, UUID(click["interaction_id"]))]

    asyncio.run(scenario())
