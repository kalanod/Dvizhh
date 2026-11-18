import argparse
import asyncio
import hashlib
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

import asyncpg
from pydantic import AwareDatetime, BaseModel, model_validator

from .dataset import _connect, _timestamp
from .embedding_encoder import ItemEncoderInput, UserEncoderInput, write_artifact

HISTORY_LIMIT = 20

_REGISTRATIONS = """
    SELECT r.user_id, r.item_id, min(r.confirmed_at) AS confirmed_at
    FROM public.recsys_confirmed_registrations AS r
    JOIN public.recsys_encoder_items AS item ON item.item_id = r.item_id
    WHERE r.confirmed_at >= $1 AND r.confirmed_at < $2
    GROUP BY r.user_id, r.item_id
    ORDER BY confirmed_at, r.user_id, r.item_id
"""
_HISTORICAL_ITEMS = """
    SELECT item_id, title, description, topic_ids
    FROM public.recsys_encoder_items WHERE item_id = ANY($1::uuid[])
    ORDER BY item_id
"""
_ACTIVE_ITEMS = """
    SELECT DISTINCT ON (item_id) item_id, title, description, topic_ids
    FROM public.recsys_catalog
    WHERE coalesce(ends_at, starts_at) >= $1::timestamptz
       OR (is_all_day AND (starts_at AT TIME ZONE timezone)::date =
           ($1::timestamptz AT TIME ZONE timezone)::date)
    ORDER BY item_id, starts_at, occurrence_id
"""


class Registration(BaseModel, extra="forbid", frozen=True):
    user_id: UUID
    item_id: UUID
    confirmed_at: AwareDatetime


class EncoderDataset(BaseModel, extra="forbid", frozen=True):
    schema_version: Literal[1] = 1
    start: AwareDatetime
    as_of: AwareDatetime
    items: tuple[ItemEncoderInput, ...]
    registrations: tuple[Registration, ...]

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        _validate_window(self.start, self.as_of)
        items = {item.item_id for item in self.items}
        if len(items) != len(self.items):
            raise ValueError("Duplicate catalogue items")
        pairs = {(row.user_id, row.item_id) for row in self.registrations}
        if len(pairs) != len(self.registrations):
            raise ValueError("Duplicate user and item registrations")
        if any(
            row.item_id not in items or not self.start <= row.confirmed_at < self.as_of
            for row in self.registrations
        ):
            raise ValueError("Registrations must reference known items in the history window")
        return self


def _validate_window(start: datetime, as_of: datetime) -> None:
    if start.utcoffset() is None or as_of.utcoffset() is None or start >= as_of:
        raise ValueError("Expected timezone-aware history start before as_of")


def _item_from_row(row: asyncpg.Record) -> ItemEncoderInput:
    return ItemEncoderInput(
        row["item_id"], row["title"], row["description"], tuple(row["topic_ids"]),
    )


async def _read_history(
    source: asyncpg.Connection, start: datetime, as_of: datetime,
) -> EncoderDataset:
    registrations = tuple(
        Registration.model_validate(dict(row))
        for row in await source.fetch(_REGISTRATIONS, start, as_of)
    )
    item_ids = sorted({row.item_id for row in registrations})
    items = tuple(
        _item_from_row(row)
        for row in await source.fetch(_HISTORICAL_ITEMS, item_ids)
    )
    return EncoderDataset(start=start, as_of=as_of, items=items, registrations=registrations)


async def read_dataset(
    source: asyncpg.Connection, start: datetime, as_of: datetime,
) -> EncoderDataset:
    _validate_window(start, as_of)
    async with source.transaction(isolation="repeatable_read", readonly=True):
        return await _read_history(source, start, as_of)


async def read_snapshot_inputs(
    source: asyncpg.Connection, start: datetime, as_of: datetime,
) -> tuple[tuple[ItemEncoderInput, ...], tuple[UserEncoderInput, ...]]:
    _validate_window(start, as_of)
    async with source.transaction(isolation="repeatable_read", readonly=True):
        history = await _read_history(source, start, as_of)
        items = tuple(
            _item_from_row(row)
            for row in await source.fetch(_ACTIVE_ITEMS, as_of)
        )
    historical_items = {item.item_id: item for item in history.items}
    histories = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
    for row in history.registrations:
        histories[row.user_id].append(historical_items[row.item_id])
    users = tuple(
        UserEncoderInput(user_id=user_id, history=tuple(histories[user_id]))
        for user_id in sorted(histories)
    )
    return items, users


async def _export(output: Path, start: datetime, as_of: datetime) -> str:
    async with _connect("SOURCE_DATABASE_URL") as source:
        data = await read_dataset(source, start, as_of)
    if not data.registrations:
        raise ValueError("No eligible confirmed registrations in the history window")
    payload = data.model_dump_json().encode()
    write_artifact(output, payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--history-start", type=_timestamp, required=True)
    parser.add_argument("--as-of", type=_timestamp, required=True)
    args = parser.parse_args()
    print(asyncio.run(_export(args.output, args.history_start, args.as_of)))


if __name__ == "__main__":
    main()
