import argparse
import asyncio
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, distinct_on
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.schema import CreateIndex

from .embedding_snapshot import EmbeddingSnapshot, catalog_content_hash
from .index_revision import find_published_revision, hnsw_index_name
from .offline import connect_database
from .retrieval import Embedding, IndexedItem
from .sql_catalog import (
    active_occurrence,
    embedding_index_versions,
    event_embeddings,
    recsys_catalog,
    user_embeddings,
)


def _coordinates(embedding: Embedding) -> list[float]:
    shape = f"{embedding.space.dimension}f"
    try:
        coordinates = struct.unpack(shape, struct.pack(shape, *embedding.values))
    except OverflowError as exc:
        raise ValueError("Embedding coordinates exceed pgvector's float32 range") from exc
    if not any(coordinates):
        raise ValueError("Cosine embeddings must remain nonzero in float32")
    return list(coordinates)


async def _catalog_items(
    source: AsyncConnection,
    snapshot: EmbeddingSnapshot,
    embeddings: dict[UUID, Embedding],
) -> tuple[list[IndexedItem], int]:
    c = recsys_catalog.c
    last_end = sa.func.max(sa.func.coalesce(c.ends_at, c.starts_at)).over(partition_by=c.item_id)
    query = (
        sa.select(
            c.item_id,
            c.title,
            c.description,
            c.price_type,
            c.format,
            c.city,
            c.latitude,
            c.longitude,
            c.topic_ids,
            sa.func.max(c.source_updated_at)
            .over(partition_by=c.item_id)
            .label("source_updated_at"),
            last_end.label("last_ends_at"),
            sa.func.min(c.starts_at).over(partition_by=c.item_id).label("next_starts_at"),
        )
        .where(
            c.item_id == sa.any_(sa.literal(list(embeddings), ARRAY(sa.Uuid))),
            active_occurrence(recsys_catalog, datetime.now(UTC), include_ending_now=False),
        )
        .ext(distinct_on(c.item_id))
        .order_by(c.item_id, c.starts_at, c.occurrence_id)
    )
    catalog = {row["item_id"]: row for row in (await source.execute(query)).mappings()}
    indexed = []
    stale = 0
    for item in snapshot.items:
        if (row := catalog.get(item.item_id)) is None:
            continue
        if item.content_hash != catalog_content_hash(
            row["title"], row["description"], row["topic_ids"]
        ):
            stale += 1
            continue
        indexed.append(
            IndexedItem(
                item_id=item.item_id,
                embedding=embeddings[item.item_id],
                content_hash=item.content_hash,
                is_candidate=True,
                source_updated_at=row["source_updated_at"],
                last_ends_at=row["last_ends_at"],
                next_starts_at=row["next_starts_at"],
                price_type=row["price_type"],
                format=row["format"],
                city=row["city"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                topic_ids=tuple(row["topic_ids"]),
            )
        )
    return indexed, stale


async def refresh_index(
    source: AsyncConnection,
    vectors: AsyncConnection,
    snapshot: EmbeddingSnapshot,
) -> dict[str, str | int]:
    space = snapshot.space
    model_id = space.model_id
    digest = hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
    revision = f"snapshot:{digest}"
    items = {item.item_id: Embedding(space=space, values=item.values) for item in snapshot.items}
    item_vectors = {item_id: _coordinates(item) for item_id, item in items.items()}
    user_rows = [
        {
            "model_name": revision,
            "user_id": user.user_id,
            "embedding": _coordinates(Embedding(space=space, values=user.values)),
        }
        for user in snapshot.users
    ]
    transaction = vectors.begin_nested() if vectors.in_transaction() else vectors.begin()
    async with transaction:
        lock = sa.func.hashtextextended("event_embeddings", sa.literal(0, sa.BigInteger))
        await vectors.execute(sa.select(sa.func.pg_advisory_xact_lock(lock)))
        published = await find_published_revision(vectors, model_id)
        if published is not None and published["generated_at"] >= snapshot.generated_at:
            if published["artifact_sha256"] != digest:
                raise ValueError("A newer or different snapshot has already been published")
            return {"revision": published["model_name"]}

        indexed, stale = await _catalog_items(source, snapshot, items)
        if not indexed:
            raise ValueError("The snapshot has no active items matching the catalogue")
        await vectors.execute(
            sa.insert(embedding_index_versions).values(
                model_name=revision,
                model_id=model_id,
                generated_at=snapshot.generated_at,
                artifact_sha256=digest,
                dimension=space.dimension,
                metric=space.metric,
            )
        )
        await vectors.execute(
            sa.insert(event_embeddings),
            [
                {
                    "event_id": item.item_id,
                    "model_name": revision,
                    "embedding": item_vectors[item.item_id],
                    "content_hash": item.content_hash,
                    "is_candidate": True,
                    "source_updated_at": item.source_updated_at,
                    "last_ends_at": item.last_ends_at,
                    "next_starts_at": item.next_starts_at,
                    "price_type": item.price_type,
                    "format": item.format,
                    "city": item.city,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "topic_ids": list(item.topic_ids),
                }
                for item in indexed
            ],
        )
        if user_rows:
            await vectors.execute(sa.insert(user_embeddings), user_rows)
        target = event_embeddings.to_metadata(sa.MetaData())
        index = sa.Index(
            hnsw_index_name(revision),
            target.c.embedding,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=sa.and_(target.c.is_candidate, target.c.model_name == revision),
        )
        await vectors.execute(CreateIndex(index))
    return {
        "revision": revision,
        "indexed_items": len(indexed),
        "stale_items": stale,
        "inactive_items": len(items) - len(indexed) - stale,
        "indexed_users": len(user_rows),
    }


async def _refresh(snapshot: EmbeddingSnapshot) -> dict[str, str | int]:
    async with (
        connect_database("SOURCE_DATABASE_URL", command_timeout=None) as source,
        connect_database("VECTOR_DATABASE_URL", command_timeout=None) as vectors,
    ):
        return await refresh_index(source, vectors, snapshot)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path, help="Complete versioned JSON embedding snapshot")
    args = parser.parse_args()
    snapshot = EmbeddingSnapshot.model_validate_json(args.snapshot.read_bytes())
    print(json.dumps(asyncio.run(_refresh(snapshot))))


if __name__ == "__main__":
    main()
