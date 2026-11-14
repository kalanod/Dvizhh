"""Populate an existing demo cohort through the API; database access is read-only.

Run inside the backend container. The default is a preflight/dry run; --apply writes.
Do not run multiple copies concurrently. Existing demo data is never overwritten.
"""

import argparse
import asyncio
import json
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from dvizh_backend.config import get_settings
from dvizh_backend.database.database_service import DatabaseService
from dvizh_backend.database.models import Event, EventOccurrence, EventParticipation, Profile
from dvizh_backend.dto.event import CreateEventDTO

BATCH = "01b944fc"
MARKER = f"[DEMO-{BATCH}-"
MOSCOW = ZoneInfo("Europe/Moscow")
CITIES = (
    ("Санкт-Петербург", "Europe/Moscow", "59.938630", "30.314130"),
    ("Москва", "Europe/Moscow", "55.755826", "37.617300"),
    ("Казань", "Europe/Moscow", "55.796127", "49.106414"),
    ("Новосибирск", "Asia/Novosibirsk", "55.008353", "82.935733"),
    ("Екатеринбург", "Asia/Yekaterinburg", "56.838011", "60.597465"),
)
TOPICS = (
    ("Акустический вечер", "music", "слушаем акустические композиции и обсуждаем музыку"),
    ("Прогулка с фотографом", "photography", "учимся замечать свет и строить кадр"),
    ("Клуб настольных игр", "board-games", "знакомимся и играем в командные настольные игры"),
    ("Лёгкая пробежка", "sport", "разминаемся и тренируемся в комфортном темпе"),
    ("Книжный разговор", "books", "обсуждаем прочитанное и делимся любимыми книгами"),
    ("Научный лекторий", "science", "разбираем научные открытия простыми словами"),
    ("Киноклуб", "cinema", "обсуждаем киноязык и впечатления от фильмов"),
    ("Танцевальная практика", "dance", "осваиваем базовые движения и импровизацию"),
    ("Кулинарная мастерская", "food", "обмениваемся рецептами и собираем сезонное меню"),
    ("Разговорный клуб", "languages", "практикуем общение на бытовые и культурные темы"),
    ("Мастерская рисунка", "art", "пробуем зарисовки и обсуждаем творческие идеи"),
    ("Встреча разработчиков", "technology", "разбираем небольшие проекты и делимся опытом"),
    ("Планируем поход", "outdoors", "обсуждаем маршруты, снаряжение и отдых на природе"),
    ("Театральная лаборатория", "theatre", "читаем сцены и тренируем сценическую речь"),
    ("Волонтёрская встреча", "volunteering", "обсуждаем идеи помощи городу и взаимоподдержки"),
)


def make_plan(users: list[dict[str, str]], anchor: date) -> list[dict[str, Any]]:
    """Build a stable plan independent of database UUIDs, apart from participant identity."""
    plan = []
    for n in range(300):
        owner = n % 50
        city, tz, latitude, longitude = CITIES[owner % 5]
        topic, tag, activity = TOPICS[(n // 5 + n % 5 * 3) % len(TOPICS)]
        event_format = ("OFFLINE", "OFFLINE", "ONLINE", "HYBRID", "OFFLINE")[n % 5]
        policy = "REQUEST" if n % 3 == 2 else "OPEN"
        start = datetime.combine(
            anchor + timedelta(days=1 + n % 90),
            time(10 + n % 10),
            tzinfo=ZoneInfo(tz),
        )
        title = f"{MARKER}{n + 1:03d}] {topic}: {city}, встреча {n // 15 + 1}"
        payload = {
            "title": title,
            "description": (
                f"Синтетическое мероприятие для проверки Движж. На встрече мы {activity}. "
                "Программа: знакомство, основная практика и обмен впечатлениями. "
                "Подходит новичкам; специальные навыки не нужны. "
                "Адрес и онлайн-ссылка демонстрационные: реального мероприятия нет. "
                + (
                    "Для участия отправьте заявку организатору."
                    if policy == "REQUEST"
                    else "Можно записаться сразу при наличии свободных мест."
                )
            ),
            "organizer_id": users[owner]["id"],
            "tags": [tag, "synthetic", f"dvizh-demo-{BATCH}"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1 + n % 3)).isoformat(),
            "timezone": tz,
            "format": event_format,
            "location": None
            if event_format == "ONLINE"
            else {
                "name": f"Демо-площадка Движж {owner % 5 + 1}",
                "city": city,
                "address_line": f"Синтетический адрес: {city}, Демо-площадка, зал {n % 6 + 1}",
                "latitude": latitude,
                "longitude": longitude,
            },
            "online_url": None
            if event_format == "OFFLINE"
            else (f"https://example.com/dvizh-demo/{BATCH}/{n + 1:03d}"),
            "price_min": None if n % 4 else str(300 + n % 8 * 100),
            "capacity": 12 + n % 5 * 4,
            "visibility": "PUBLIC",
            "join_policy": policy,
        }
        # Validate the same DTO that the API receives, before any mutations.
        normalized = CreateEventDTO.model_validate(payload).model_dump(mode="json")
        going = 3 if policy == "REQUEST" else 4 + n % 7
        pending = 2 + n % 4 if policy == "REQUEST" else 0
        participants = {
            users[(owner + step) % 50]["id"]: "GOING" if step <= going else "REQUESTED"
            for step in range(1, going + pending + 1)
        }
        plan.append({"payload": normalized, "participants": participants})
    return plan


def api(base: str, path: str, data: dict | None = None, method: str | None = None) -> Any:
    request = urllib.request.Request(
        base + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API {request.method} {path}: HTTP {exc.code}") from None


async def discover() -> tuple[list[dict], dict[str, str], date]:
    database = DatabaseService(get_settings().database_url)
    try:
        async with database.session_factory() as session:
            profiles = (
                await session.scalars(
                    select(Profile)
                    .where(Profile.username.startswith(f"demo_{BATCH}_"))
                    .order_by(Profile.username)
                )
            ).all()
            expected = [f"demo_{BATCH}_{n:02d}" for n in range(1, 51)]
            if [p.username for p in profiles] != expected:
                raise RuntimeError("Exactly the expected 50 demo profiles must exist")
            if any(p.status.value != "ACTIVE" for p in profiles):
                raise RuntimeError("All demo profiles must be active")
            events = (
                await session.scalars(select(Event).where(Event.title.startswith(MARKER)))
            ).all()
            titles = {event.title: str(event.id) for event in events}
            if len(titles) != len(events):
                raise RuntimeError("Duplicate demo event titles; no data changed")
            anchor = (
                min(e.created_at for e in events).astimezone(MOSCOW).date()
                if events
                else (datetime.now(MOSCOW).date())
            )
            return [{"id": str(p.id), "username": p.username} for p in profiles], titles, anchor
    finally:
        await database.dispose()


def verify_event(event: dict, payload: dict) -> None:
    if event["status"] != "PUBLISHED" or event["organizer"]["id"] != payload["organizer_id"]:
        raise RuntimeError(f"Conflicting demo event ownership/status: {event['id']}")
    for field in (
        "title",
        "description",
        "timezone",
        "format",
        "online_url",
        "capacity",
        "visibility",
        "join_policy",
        "is_all_day",
    ):
        if event[field] != payload[field]:
            raise RuntimeError(f"Conflicting demo event {field}: {event['id']}")
    for field in ("starts_at", "ends_at"):
        if datetime.fromisoformat(event[field]) != datetime.fromisoformat(payload[field]):
            raise RuntimeError(f"Conflicting demo event {field}: {event['id']}")
    if set(event["tags"]) != set(payload["tags"]):
        raise RuntimeError(f"Conflicting demo tags: {event['id']}")
    expected_price = payload["price_min"]
    same_price = (event["price_min"] is None and expected_price is None) or (
        event["price_min"] is not None
        and expected_price is not None
        and Decimal(event["price_min"]) == Decimal(expected_price)
    )
    if not same_price or event["price_max"] is not None:
        raise RuntimeError(f"Conflicting demo prices: {event['id']}")
    if event["location"] != payload["location"]:
        raise RuntimeError(f"Conflicting demo location: {event['id']}")


async def verify_database(expected: dict[str, dict[str, str]]) -> Counter:
    database = DatabaseService(get_settings().database_url)
    try:
        async with database.session_factory() as session:
            rows = (
                await session.execute(
                    select(Event.id, EventParticipation.user_id, EventParticipation.status)
                    .join(EventOccurrence, EventOccurrence.event_id == Event.id)
                    .join(
                        EventParticipation, EventParticipation.occurrence_id == EventOccurrence.id
                    )
                    .where(Event.title.startswith(MARKER))
                )
            ).all()
            actual = {
                (str(event_id), str(user_id)): status.value for event_id, user_id, status in rows
            }
            planned = {
                (event_id, user_id): status
                for event_id, people in expected.items()
                for user_id, status in people.items()
            }
            if actual != planned:
                raise RuntimeError("Database participation verification differs from plan")
            return Counter(actual.values())
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create events and participations")
    parser.add_argument(
        "--verify-only", action="store_true", help="Require a complete existing set"
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    if args.apply and args.verify_only:
        parser.error("--apply and --verify-only are mutually exclusive")
    users, existing, anchor = asyncio.run(discover())
    plan = make_plan(users, anchor)
    expected_titles = {item["payload"]["title"] for item in plan}
    if set(existing) - expected_titles:
        raise RuntimeError("Unexpected event in demo namespace; no data changed")
    api(args.base_url, "/api/health")
    cached = {}
    # Validate the complete existing subset before writing anything.
    for item in plan:
        title = item["payload"]["title"]
        if title in existing:
            event_id = existing[title]
            event = api(args.base_url, f"/api/events/{event_id}")
            verify_event(event, item["payload"])
            people = api(args.base_url, f"/api/events/{event_id}/participants")
            states = {p["user"]["id"]: p["status"] for p in people}
            for user_id, status in states.items():
                wanted = item["participants"].get(user_id)
                resumable = (status, wanted) == ("REQUESTED", "GOING")
                if wanted is None or (status != wanted and not resumable):
                    raise RuntimeError(f"Conflicting demo participation: {event_id}")
            cached[event_id] = states
    totals = Counter(status for item in plan for status in item["participants"].values())
    summary = {
        "batch": BATCH,
        "mode": "apply" if args.apply else "dry-run",
        "anchor_date": str(anchor),
        "events": len(plan),
        "existing_events": len(existing),
        "organizers": len(users),
        "events_per_organizer": 6,
        "policies": dict(Counter(item["payload"]["join_policy"] for item in plan)),
        "expected_participations": dict(totals),
        "first_start": min(item["payload"]["starts_at"] for item in plan),
        "last_start": max(item["payload"]["starts_at"] for item in plan),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if args.verify_only:
        if len(existing) != 300:
            raise RuntimeError("Verification requires all 300 demo events")
        expected = {existing[item["payload"]["title"]]: item["participants"] for item in plan}
        actual = asyncio.run(verify_database(expected))
        summary.update(
            {"mode": "verify-only", "verified_participations": dict(actual), "verified": True}
        )
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        return
    if not args.apply:
        return
    expected = {}
    created = joined = approved = 0
    for index, item in enumerate(plan, 1):
        payload = item["payload"]
        event_id = existing.get(payload["title"])
        if event_id is None:
            event = api(args.base_url, "/api/events", payload)
            verify_event(event, payload)
            event_id = event["id"]
            created += 1
        states = cached.get(event_id, {})
        for user_id, desired in item["participants"].items():
            status = states.get(user_id)
            if status is None:
                result = api(
                    args.base_url, f"/api/events/{event_id}/participants", {"user_id": user_id}
                )
                status = result["status"]
                joined += 1
            if desired == "GOING" and status == "REQUESTED":
                result = api(
                    args.base_url,
                    f"/api/events/{event_id}/participants/{user_id}",
                    {"actor_id": payload["organizer_id"], "accept": True},
                    "PATCH",
                )
                status = result["status"]
                approved += 1
            if status != desired:
                raise RuntimeError(f"Unexpected participation result: {event_id}")
        expected[event_id] = item["participants"]
        if index % 25 == 0:
            print(json.dumps({"processed": index, "created": created}), flush=True)
    actual = asyncio.run(verify_database(expected))
    final_users, final_events, _ = asyncio.run(discover())
    if len(final_events) != 300 or len(final_users) != 50 or actual != totals:
        raise RuntimeError("Final dataset totals differ from plan")
    summary.update(
        {
            "created": created,
            "joined": joined,
            "approved": approved,
            "verified_participations": dict(actual),
            "verified": True,
        }
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
