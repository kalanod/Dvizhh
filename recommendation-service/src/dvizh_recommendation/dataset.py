import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, JsonValue
from sqlalchemy import DateTime, RowMapping, Uuid, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncConnection

from .database import read_snapshot
from .feedback_tables import (
    recommendation_pages,
    recsys_confirmed_registrations,
    recsys_interactions,
    recsys_participation_history,
)
from .offline import connect_database, parse_timestamp


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


def _feedback_key(record: RowMapping) -> tuple[str, str, str, str]:
    return tuple(str(record[key]) for key in ("user_id", "session_id", "request_id", "item_id"))


type _Feedback = dict[tuple[str, str, str, str], list[RowMapping]]


async def _read_feedback(
    source: AsyncConnection,
    request_ids: list[UUID],
    as_of: datetime,
) -> tuple[_Feedback, _Feedback]:
    impressions = defaultdict(list)
    registrations = defaultdict(list)
    action = recsys_interactions.c
    booking = recsys_confirmed_registrations.c
    eligible = (action.request_id.in_(request_ids), action.received_at < as_of)
    shows = (
        select(
            action.user_id,
            action.session_id,
            action.request_id,
            action.item_id,
            action.occurrence_id,
            action.occurred_at,
            action.received_at,
        )
        .where(*eligible, action.event_type == "IMPRESSION")
        .order_by(action.occurred_at, action.received_at, action.interaction_id)
    )
    bookings = (
        select(
            action.user_id,
            action.session_id,
            action.request_id,
            action.item_id,
            booking.occurrence_id,
            action.occurred_at.label("clicked_at"),
            action.received_at,
            booking.confirmed_at,
        )
        .join_from(
            recsys_interactions,
            recsys_confirmed_registrations,
            (booking.origin_interaction_id == action.interaction_id)
            & (booking.user_id == action.user_id)
            & (booking.item_id == action.item_id),
        )
        .where(*eligible, action.event_type == "JOIN_CLICK", booking.confirmed_at < as_of)
    )
    for impression in (await source.execute(shows)).mappings():
        impressions[_feedback_key(impression)].append(impression)
    for registration in (await source.execute(bookings)).mappings():
        registrations[_feedback_key(registration)].append(registration)
    return impressions, registrations


async def _already_registered(
    source: AsyncConnection,
    observed_items: Sequence[_ObservedItem],
) -> set[int]:
    shown = (
        func.unnest(
            literal([row.user_id for row in observed_items], ARRAY(Uuid)),
            literal([row.item.occurrence_id for row in observed_items], ARRAY(Uuid)),
            literal([row.shown_at for row in observed_items], ARRAY(DateTime(timezone=True))),
        )
        .table_valued("user_id", "occurrence_id", "shown_at", with_ordinality="ordinality")
        .render_derived(name="shown")
    )
    history = recsys_participation_history.c
    status_at_show = (
        select(history.status)
        .where(
            history.user_id == shown.c.user_id,
            history.occurrence_id == shown.c.occurrence_id,
            history.changed_at <= shown.c.shown_at,
        )
        .order_by(history.changed_at.desc(), history.change_id.desc())
        .limit(1)
        .correlate(shown)
        .scalar_subquery()
    )
    return set(await source.scalars(select(shown.c.ordinality).where(status_at_show == "GOING")))


async def _examples(
    source: AsyncConnection,
    pages: Sequence[RowMapping],
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
    impressions, registrations = await _read_feedback(source, request_ids, window.as_of)

    observed_items: list[_ObservedItem] = []
    for page, ids in page_keys:
        for position, payload in enumerate(page["items"]):
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
            observed_items.append(
                _ObservedItem(
                    user_id=ids[0],
                    request_id=page["request_id"],
                    item=item,
                    position=position,
                    shown_at=max(page["served_at"], min(shown_at, received_at)),
                    served_at=page["served_at"],
                    split=split,
                    label=label,
                )
            )

    if not observed_items:
        return
    already_going = await _already_registered(source, observed_items)
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
    source: AsyncConnection,
    journal: AsyncConnection,
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
            page = recommendation_pages.c
            statement = (
                select(
                    page.request_id, page.session_id, page.user_id, page.served_at, page["items"]
                )
                .where(page.served_at >= window.start, page.served_at < window.as_of)
                .order_by(page.served_at, page.request_id)
            )
            async with (
                read_snapshot(journal),
                read_snapshot(source),
                journal.stream(statement.execution_options(yield_per=200)) as rows,
            ):
                async for pages in rows.mappings().partitions(200):
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


async def _run(args: argparse.Namespace) -> str:
    window = DatasetWindow(
        args.start,
        args.validation_start,
        args.test_start,
        args.as_of,
        timedelta(hours=args.observation_hours),
    )
    async with (
        connect_database("SOURCE_DATABASE_URL") as source,
        connect_database("VECTOR_DATABASE_URL") as journal,
    ):
        return await export_dataset(source, journal, args.output, window, args.feature_version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    for boundary in ("start", "validation-start", "test-start", "as-of"):
        parser.add_argument(f"--{boundary}", required=True, type=parse_timestamp)
    parser.add_argument("--observation-hours", required=True, type=float)
    parser.add_argument("--feature-version", required=True)
    print(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
