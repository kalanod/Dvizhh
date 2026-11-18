import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from datetime import datetime
from itertools import batched
from pathlib import Path

from .dataset import _connect, _timestamp
from .embedding_encoder import (
    EmbeddingEncoder,
    ItemEncoderInput,
    UserEncoderInput,
    load_encoder,
    write_artifact,
)
from .encoder_data import read_snapshot_inputs
from .retrieval import Embedding
from .vector_index import EmbeddingSnapshot, ItemVector, UserVector, catalog_content_hash

_BATCH_SIZE = 256


def build_snapshot(
    encoder: EmbeddingEncoder,
    items: Sequence[ItemEncoderInput],
    users: Sequence[UserEncoderInput],
    *,
    generated_at: datetime,
) -> EmbeddingSnapshot:
    if not items or not users:
        raise ValueError("An embedding snapshot requires active items and users with history")
    if any(not user.history for user in users):
        raise ValueError("Users without history cannot be encoded")
    space = encoder.space
    item_vectors = []
    for batch in batched(items, _BATCH_SIZE):
        for item, vector in zip(batch, encoder.encode_items(batch), strict=True):
            item_vectors.append(ItemVector(
                item_id=item.item_id,
                content_hash=catalog_content_hash(item.title, item.description, item.topic_ids),
                values=Embedding(space=space, values=tuple(vector)).values,
            ))

    user_vectors = []
    for batch in batched(users, _BATCH_SIZE):
        for user, vector in zip(batch, encoder.encode_users(batch), strict=True):
            user_vectors.append(UserVector(
                user_id=user.user_id,
                values=Embedding(space=space, values=tuple(vector)).values,
            ))

    return EmbeddingSnapshot(
        space=space,
        generated_at=generated_at,
        items=tuple(item_vectors),
        users=tuple(user_vectors),
    )


def write_snapshot(snapshot: EmbeddingSnapshot, output: Path) -> None:
    write_artifact(output, snapshot.model_dump_json().encode())


async def _inputs(
    start: datetime, as_of: datetime,
) -> tuple[tuple[ItemEncoderInput, ...], tuple[UserEncoderInput, ...]]:
    async with _connect("SOURCE_DATABASE_URL") as source:
        return await read_snapshot_inputs(source, start, as_of)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("uri", help="Exact MLflow model URI: models:/<name>/<version>")
    parser.add_argument("output", type=Path)
    parser.add_argument("--history-start", required=True, type=_timestamp)
    parser.add_argument("--as-of", required=True, type=_timestamp)
    args = parser.parse_args()
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        parser.error("MLFLOW_TRACKING_URI is required")
    if args.history_start >= args.as_of:
        parser.error("--history-start must precede --as-of")

    encoder = load_encoder(args.uri)
    items, users = asyncio.run(_inputs(args.history_start, args.as_of))
    snapshot = build_snapshot(encoder, items, users, generated_at=args.as_of)
    write_snapshot(snapshot, args.output)
    print(json.dumps({
        "model_id": snapshot.space.model_id, "items": len(items), "users": len(users),
    }))


if __name__ == "__main__":
    main()
