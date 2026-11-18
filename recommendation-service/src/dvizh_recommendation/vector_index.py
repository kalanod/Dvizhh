import argparse
import asyncio
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from .embedding_snapshot import EmbeddingSnapshot, catalog_content_hash
from .index_revision import find_published_revision, hnsw_index_name
from .offline import connect_database
from .retrieval import Embedding, IndexedItem

_CATALOG = """
SELECT DISTINCT ON (item_id) item_id, title, description, price_type, format, city,
       latitude, longitude, topic_ids,
       max(source_updated_at) OVER (PARTITION BY item_id) AS source_updated_at,
       max(coalesce(ends_at, starts_at)) OVER (PARTITION BY item_id) AS last_ends_at,
       min(starts_at) OVER (PARTITION BY item_id) AS next_starts_at
FROM public.recsys_catalog
WHERE item_id = ANY($1::uuid[])
  AND (ends_at > $2::timestamptz OR (ends_at IS NULL AND starts_at >= $2) OR (
       is_all_day AND (starts_at AT TIME ZONE timezone)::date =
           ($2::timestamptz AT TIME ZONE timezone)::date))
ORDER BY item_id, starts_at, occurrence_id
"""

_INSERT_ITEM = """
INSERT INTO public.event_embeddings (
    event_id, model_name, embedding, content_hash, is_candidate, source_updated_at,
    last_ends_at, next_starts_at, price_type, format, city, latitude, longitude, topic_ids
) VALUES ($1, $2, $3::text::vector, $4, true, $5, $6, $7, $8, $9, $10, $11, $12, $13)
"""

def _vector_text(embedding: Embedding) -> str:
    shape = f"{embedding.space.dimension}f"
    try:
        coordinates = struct.unpack(shape, struct.pack(shape, *embedding.values))
    except OverflowError as exc:
        raise ValueError("Embedding coordinates exceed pgvector's float32 range") from exc
    if not any(coordinates):
        raise ValueError("Cosine embeddings must remain nonzero in float32")
    return json.dumps(coordinates, separators=(",", ":"))


async def _catalog_items(
    source: asyncpg.Connection, snapshot: EmbeddingSnapshot, embeddings: dict[UUID, Embedding]
) -> tuple[list[IndexedItem], int]:
    catalog = {
        row["item_id"]: row
        for row in await source.fetch(_CATALOG, list(embeddings), datetime.now(UTC))
    }
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
    source: asyncpg.Connection, vectors: asyncpg.Connection, snapshot: EmbeddingSnapshot
) -> dict[str, str | int]:
    space = snapshot.space
    model_id = space.model_id
    digest = hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
    revision = f"snapshot:{digest}"
    items = {item.item_id: Embedding(space=space, values=item.values) for item in snapshot.items}
    item_vectors = {item_id: _vector_text(item) for item_id, item in items.items()}
    user_rows = [
        (revision, user.user_id, _vector_text(Embedding(space=space, values=user.values)))
        for user in snapshot.users
    ]
    async with vectors.transaction():
        await vectors.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('event_embeddings', 0))"
        )
        published = await find_published_revision(vectors, model_id)
        if published is not None and published["generated_at"] >= snapshot.generated_at:
            if published["artifact_sha256"] != digest:
                raise ValueError("A newer or different snapshot has already been published")
            return {"revision": published["model_name"]}

        indexed, stale = await _catalog_items(source, snapshot, items)
        if not indexed:
            raise ValueError("The snapshot has no active items matching the catalogue")
        await vectors.execute(
            """
            INSERT INTO public.embedding_index_versions
                (model_name, model_id, generated_at, artifact_sha256, dimension, metric)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            revision,
            model_id,
            snapshot.generated_at,
            digest,
            space.dimension,
            space.metric,
        )
        await vectors.executemany(
            _INSERT_ITEM,
            [
                (
                    item.item_id,
                    revision,
                    item_vectors[item.item_id],
                    item.content_hash,
                    item.source_updated_at,
                    item.last_ends_at,
                    item.next_starts_at,
                    item.price_type,
                    item.format,
                    item.city,
                    item.latitude,
                    item.longitude,
                    list(item.topic_ids),
                )
                for item in indexed
            ],
        )
        await vectors.executemany(
            "INSERT INTO public.user_embeddings VALUES ($1, $2, $3::text::vector)",
            user_rows,
        )
        literal = await vectors.fetchval("SELECT quote_literal($1::text)", revision)
        await vectors.execute(
            f"CREATE INDEX {hnsw_index_name(revision)} "
            "ON public.event_embeddings USING hnsw (embedding vector_cosine_ops) "
            f"WHERE is_candidate AND model_name = {literal}"
        )
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
