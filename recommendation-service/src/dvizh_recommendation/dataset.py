import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import asyncpg
from pydantic import AwareDatetime, BaseModel, JsonValue

_PAGES = """
SELECT request_id, session_id, user_id, served_at, items
FROM public.recommendation_pages
WHERE served_at >= $1 AND served_at < $2
ORDER BY served_at, request_id
"""
_IMPRESSIONS = """
SELECT user_id, session_id, request_id, item_id, occurrence_id, occurred_at, received_at
FROM public.recsys_interactions
WHERE request_id = ANY($1::uuid[]) AND event_type = 'IMPRESSION'
  AND received_at < $2
ORDER BY occurred_at, received_at, interaction_id
"""
_REGISTRATIONS = """
SELECT i.user_id, i.session_id, i.request_id, i.item_id, g.occurrence_id,
       i.occurred_at AS clicked_at, i.received_at, g.confirmed_at
FROM public.recsys_interactions i
JOIN public.recsys_confirmed_registrations g
  ON g.origin_interaction_id = i.interaction_id
 AND g.user_id = i.user_id AND g.item_id = i.item_id
WHERE i.request_id = ANY($1::uuid[]) AND i.event_type = 'JOIN_CLICK'
  AND i.received_at < $2 AND g.confirmed_at < $2
"""
_ALREADY_GOING = """
SELECT impression.ordinality
FROM unnest($1::uuid[], $2::uuid[], $3::timestamptz[]) WITH ORDINALITY
     AS impression(user_id, occurrence_id, shown_at, ordinality)
JOIN LATERAL (
    SELECT status
    FROM public.recsys_participation_history AS h
    WHERE h.user_id = impression.user_id AND h.occurrence_id = impression.occurrence_id
      AND h.changed_at <= impression.shown_at
    ORDER BY h.changed_at DESC, h.change_id DESC
    LIMIT 1
) AS last_change ON last_change.status = 'GOING'
"""


class _ScoredItem(BaseModel):
    item_id: UUID
    occurrence_id: UUID | None = None
    feature_version: str | None = None
    features: dict[str, JsonValue] | None = None
    calculated_at: AwareDatetime | None = None
    algorithm_version: str | None = None


@dataclass(frozen=True)
class _ObservedItem:
    user_id: UUID
    request_id: str
    item: _ScoredItem
    position: int
    shown_at: datetime
    served_at: datetime
    split: str
    label: bool


@dataclass(frozen=True)
class DatasetWindow:
    start: datetime
    validation_start: datetime
    test_start: datetime
    as_of: datetime
    observation_window: timedelta

    def __post_init__(self) -> None:
        boundaries = (self.start, self.validation_start, self.test_start, self.as_of)
        if any(value.utcoffset() is None for value in boundaries):
            raise ValueError("Dataset boundaries must include a time zone")
        if not self.start < self.validation_start < self.test_start < self.as_of:
            raise ValueError("Expected start < validation_start < test_start < as_of")
        if self.observation_window <= timedelta(0):
            raise ValueError("Observation window must be positive")

    def split(self, at: datetime) -> tuple[str, datetime]:
        if at < self.validation_start:
            return "train", self.validation_start
        if at < self.test_start:
            return "validation", self.test_start
        return "test", self.as_of


def _feedback_key(record: asyncpg.Record) -> tuple[str, str, str, str]:
    return tuple(str(record[key]) for key in ("user_id", "session_id", "request_id", "item_id"))


async def _examples(
    source: asyncpg.Connection,
    pages: list[asyncpg.Record],
    window: DatasetWindow,
    feature_version: str,
    counts: Counter[str],
) -> AsyncIterator[dict[str, object]]:
    page_keys = []
    for page in pages:
        try:
            ids = tuple(UUID(page[name]) for name in ("user_id", "session_id", "request_id"))
        except ValueError:
            counts["unattributable_pages"] += 1
        else:
            page_keys.append((page, ids))
    if not page_keys:
        return
    request_ids = list({ids[2] for _, ids in page_keys})
    impressions = defaultdict(list)
    registrations = defaultdict(list)
    for impression in await source.fetch(_IMPRESSIONS, request_ids, window.as_of):
        impressions[_feedback_key(impression)].append(impression)
    for registration in await source.fetch(_REGISTRATIONS, request_ids, window.as_of):
        registrations[_feedback_key(registration)].append(registration)

    observed_items: list[_ObservedItem] = []
    for page, ids in page_keys:
        for position, payload in enumerate(json.loads(page["items"])):
            item = _ScoredItem.model_validate(payload)
            if item.feature_version != feature_version or item.features is None:
                counts["different_feature_version"] += 1
                continue
            if item.features.get("join_policy") in {"EXTERNAL", "INVITE_ONLY"}:
                counts["unobservable_booking"] += 1
                continue
            key = (*map(str, ids), str(item.item_id))
            checked_impressions = [
                hit
                for hit in impressions[key]
                if hit["occurrence_id"] is None or hit["occurrence_id"] == item.occurrence_id
            ]
            if not checked_impressions:
                counts["not_shown"] += 1
                continue
            shown_at = checked_impressions[0]["occurred_at"]
            received_at = checked_impressions[0]["received_at"]
            split, cutoff = window.split(page["served_at"])
            deadline = max(page["served_at"], received_at) + window.observation_window
            if deadline >= cutoff:
                counts["unobserved_window"] += 1
                continue
            label = any(
                hit["received_at"] < cutoff
                and shown_at <= hit["clicked_at"]
                and page["served_at"] <= hit["confirmed_at"] <= deadline
                and hit["occurrence_id"] == item.occurrence_id
                for hit in registrations[key]
            )
            observed_items.append(_ObservedItem(
                user_id=ids[0],
                request_id=page["request_id"],
                item=item,
                position=position,
                shown_at=max(page["served_at"], min(shown_at, received_at)),
                served_at=page["served_at"],
                split=split,
                label=label,
            ))

    if not observed_items:
        return
    rows = await source.fetch(
        _ALREADY_GOING,
        [observed.user_id for observed in observed_items],
        [observed.item.occurrence_id for observed in observed_items],
        [observed.shown_at for observed in observed_items],
    )
    already_going = {row["ordinality"] for row in rows}
    for ordinal, observed in enumerate(observed_items, start=1):
        if ordinal in already_going:
            counts["already_registered"] += 1
            continue
        counts[observed.split] += 1
        counts[f"{observed.split}_positive"] += observed.label
        item = observed.item
        yield {
            "split": observed.split,
            "request_id": observed.request_id,
            "item_id": str(item.item_id),
            "position": observed.position,
            "served_at": observed.served_at.isoformat(),
            "calculated_at": item.calculated_at.isoformat() if item.calculated_at else None,
            "algorithm_version": item.algorithm_version,
            "features": item.features,
            "label": int(observed.label),
        }


async def export_dataset(
    source: asyncpg.Connection,
    journal: asyncpg.Connection,
    output: Path,
    window: DatasetWindow,
    feature_version: str,
) -> str:
    if output.exists():
        raise FileExistsError(f"Dataset already exists: {output}")
    counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    with TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory) / "dataset"
        staging.mkdir()
        with (staging / "examples.jsonl").open("wb") as stream:
            async with (
                journal.transaction(isolation="repeatable_read", readonly=True),
                source.transaction(isolation="repeatable_read", readonly=True),
            ):
                cursor = await journal.cursor(_PAGES, window.start, window.as_of)
                while pages := await cursor.fetch(200):
                    async for row in _examples(source, pages, window, feature_version, counts):
                        line = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode()
                        stream.write(line)
                        digest.update(line)
        manifest = {
            "schema_version": 1,
            "feature_version": feature_version,
            "start": window.start.isoformat(),
            "validation_start": window.validation_start.isoformat(),
            "test_start": window.test_start.isoformat(),
            "as_of": window.as_of.isoformat(),
            "observation_seconds": window.observation_window.total_seconds(),
            "examples_sha256": digest.hexdigest(),
            "counts": dict(counts),
        }
        version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        manifest["dataset_version"] = version
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(output)
    return version


@asynccontextmanager
async def _connect(variable: str) -> AsyncIterator[asyncpg.Connection]:
    url = os.environ.get(variable)
    if not url:
        raise ValueError(f"{variable} is required")
    try:
        connection = await asyncpg.connect(url, timeout=5, command_timeout=30)
    except Exception as exc:
        raise RuntimeError(f"Cannot connect using {variable} ({type(exc).__name__})") from None
    try:
        yield connection
    finally:
        await connection.close(timeout=5)


def _timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise argparse.ArgumentTypeError("A time zone is required")
    return timestamp.astimezone(UTC)


async def _run(args: argparse.Namespace) -> str:
    window = DatasetWindow(
        args.start,
        args.validation_start,
        args.test_start,
        args.as_of,
        timedelta(hours=args.observation_hours),
    )
    async with (
        _connect("SOURCE_DATABASE_URL") as source,
        _connect("VECTOR_DATABASE_URL") as journal,
    ):
        return await export_dataset(source, journal, args.output, window, args.feature_version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    for boundary in ("start", "validation-start", "test-start", "as-of"):
        parser.add_argument(f"--{boundary}", required=True, type=_timestamp)
    parser.add_argument("--observation-hours", required=True, type=float)
    parser.add_argument("--feature-version", required=True)
    print(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
