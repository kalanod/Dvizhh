import argparse
import asyncio
import hashlib
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, model_validator
from sqlalchemy import RowMapping, Uuid, any_, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY, distinct_on
from sqlalchemy.ext.asyncio import AsyncConnection

from .database import read_snapshot
from .embedding_encoder import ItemEncoderInput, UserEncoderInput, write_artifact
from .feedback_tables import recsys_confirmed_registrations, recsys_encoder_items
from .offline import connect_database, parse_timestamp
from .sql_catalog import active_occurrence, recsys_catalog

HISTORY_LIMIT = 20


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


def _item_from_row(row: RowMapping) -> ItemEncoderInput:
    return ItemEncoderInput(
        row["item_id"],
        row["title"],
        row["description"],
        tuple(row["topic_ids"]),
    )


async def _read_history(
    source: AsyncConnection,
    start: datetime,
    as_of: datetime,
) -> EncoderDataset:
    booking = recsys_confirmed_registrations.c
    item = recsys_encoder_items.c
    first_booking = func.min(booking.confirmed_at).label("confirmed_at")
    statement = (
        select(booking.user_id, booking.item_id, first_booking)
        .join_from(
            recsys_confirmed_registrations, recsys_encoder_items, item.item_id == booking.item_id
        )
        .where(booking.confirmed_at >= start, booking.confirmed_at < as_of)
        .group_by(booking.user_id, booking.item_id)
        .order_by(first_booking, booking.user_id, booking.item_id)
    )
    registrations = tuple(
        Registration.model_validate(row) for row in (await source.execute(statement)).mappings()
    )
    item_ids = sorted({row.item_id for row in registrations})
    historical_items = (
        select(item.item_id, item.title, item.description, item.topic_ids)
        .where(item.item_id == any_(literal(item_ids, ARRAY(Uuid))))
        .order_by(item.item_id)
    )
    items = tuple(
        _item_from_row(row) for row in (await source.execute(historical_items)).mappings()
    )
    return EncoderDataset(start=start, as_of=as_of, items=items, registrations=registrations)


async def read_dataset(
    source: AsyncConnection,
    start: datetime,
    as_of: datetime,
) -> EncoderDataset:
    _validate_window(start, as_of)
    async with read_snapshot(source):
        return await _read_history(source, start, as_of)


async def read_snapshot_inputs(
    source: AsyncConnection,
    start: datetime,
    as_of: datetime,
) -> tuple[tuple[ItemEncoderInput, ...], tuple[UserEncoderInput, ...]]:
    _validate_window(start, as_of)
    async with read_snapshot(source):
        history = await _read_history(source, start, as_of)
        item = recsys_catalog.c
        statement = (
            select(item.item_id, item.title, item.description, item.topic_ids)
            .ext(distinct_on(item.item_id))
            .where(active_occurrence(recsys_catalog, as_of))
            .order_by(item.item_id, item.starts_at, item.occurrence_id)
        )
        items = tuple(_item_from_row(row) for row in (await source.execute(statement)).mappings())
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
    async with connect_database("SOURCE_DATABASE_URL") as source:
        data = await read_dataset(source, start, as_of)
    if not data.registrations:
        raise ValueError("No eligible confirmed registrations in the history window")
    payload = data.model_dump_json().encode()
    write_artifact(output, payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--history-start", type=parse_timestamp, required=True)
    parser.add_argument("--as-of", type=parse_timestamp, required=True)
    args = parser.parse_args()
    print(asyncio.run(_export(args.output, args.history_start, args.as_of)))


if __name__ == "__main__":
    main()
