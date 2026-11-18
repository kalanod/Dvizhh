import argparse
import asyncio
import hashlib
import json
import os
import struct
from collections.abc import Sequence
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import UUID

import asyncpg
from pydantic import AwareDatetime, BaseModel, Field, FiniteFloat, model_validator

from .recommendations import Candidate, CandidateBatch, NoUserVector, RecommendationQuery
from .retrieval import Embedding, EmbeddingSpace, IndexedItem, ScoredItem

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

_PUBLISHED_INDEX = """
SELECT model_name, generated_at, artifact_sha256, dimension, metric
FROM public.embedding_index_versions
WHERE (model_id = $1 OR (model_id IS NULL AND model_name = $1))
  AND ($2::text IS NULL OR model_name = $2)
ORDER BY generated_at DESC
LIMIT 1
"""


class ItemVector(BaseModel, extra="forbid", frozen=True):
    item_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: tuple[FiniteFloat, ...]


class UserVector(BaseModel, extra="forbid", frozen=True):
    user_id: UUID
    values: tuple[FiniteFloat, ...]


class EmbeddingSnapshot(BaseModel, extra="forbid", frozen=True):
    space: EmbeddingSpace
    generated_at: AwareDatetime
    items: tuple[ItemVector, ...]
    users: tuple[UserVector, ...]

    @model_validator(mode="after")
    def validate_space_and_ids(self) -> Self:
        if self.space.dimension != 384 or self.space.metric != "cosine":
            raise ValueError("The index requires 384-dimensional cosine embeddings")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("Embedding snapshot contains duplicate item IDs")
        if len({user.user_id for user in self.users}) != len(self.users):
            raise ValueError("Embedding snapshot contains duplicate user IDs")
        return self


def catalog_content_hash(title: str, description: str, topic_ids: Sequence[UUID]) -> str:
    payload = [title, description, sorted(map(str, topic_ids))]
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


def _index_name(model_id: str) -> str:
    digest = hashlib.sha256(model_id.encode()).hexdigest()[:32]
    return f"event_embeddings_hnsw_{digest}"


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
        published = await vectors.fetchrow(_PUBLISHED_INDEX, model_id, None)
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
            f"CREATE INDEX {_index_name(revision)} "
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


class HnswCandidates:
    def __init__(self, pool: asyncpg.Pool, model_id: str, revision: str | None = None) -> None:
        self.pool = pool
        self.model_id = model_id
        self.revision = revision

    async def check_ready(self) -> bool:
        published = await self.pool.fetchrow(_PUBLISHED_INDEX, self.model_id, self.revision)
        if published is None or published["dimension"] != 384 or published["metric"] != "cosine":
            return False
        revision = published["model_name"]
        if not await self.pool.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_index JOIN pg_class ON oid = indexrelid
                JOIN pg_am ON pg_am.oid = pg_class.relam
                WHERE indexrelid = to_regclass($1) AND indisvalid AND indisready
                  AND amname = 'hnsw'
                  AND indrelid = 'public.event_embeddings'::regclass
            )
            """,
            f"public.{_index_name(revision)}",
        ):
            return False
        self.revision = revision
        return True

    async def generate(
        self,
        query: RecommendationQuery,
        *,
        limit: int,
        exclude_ids: Sequence[UUID],
        eligible_ids: Sequence[UUID] | None = None,
    ) -> CandidateBatch:
        if limit <= 0:
            raise ValueError("Candidate limit must be positive")
        if eligible_ids is not None and not eligible_ids:
            return CandidateBatch((), exhausted=True)
        viewer = query.viewer_id
        if viewer is None:
            raise NoUserVector
        excluded = list(exclude_ids)
        eligible = None if eligible_ids is None else list(eligible_ids)
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            user = await connection.fetchrow(
                "SELECT embedding::text AS embedding, quote_literal(model_name) AS version "
                "FROM public.user_embeddings WHERE model_name = $1 AND user_id = $2",
                self.revision,
                viewer,
            )
            if user is None:
                raise NoUserVector
            await connection.execute("SET LOCAL hnsw.iterative_scan = 'strict_order'")
            rows = await connection.fetch(
                f"""
                WITH nearest AS MATERIALIZED (
                    SELECT event_id, embedding <=> $1::text::vector AS distance
                    FROM public.event_embeddings
                    WHERE is_candidate AND model_name = {user["version"]}
                        AND NOT (event_id = ANY($3::uuid[]))
                        AND ($4::uuid[] IS NULL OR event_id = ANY($4))
                    ORDER BY embedding <=> $1::text::vector
                    LIMIT $2
                )
                SELECT event_id AS item_id, 1 - distance AS retrieval_score
                FROM nearest ORDER BY distance, event_id
                """,
                user["embedding"],
                limit,
                excluded,
                eligible,
            )
            has_more = len(rows) == limit or await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM public.event_embeddings
                    WHERE is_candidate AND model_name = $1
                        AND NOT (event_id = ANY($2::uuid[]))
                        AND ($3::uuid[] IS NULL OR event_id = ANY($3))
                )
                """,
                self.revision,
                excluded + [row["item_id"] for row in rows],
                eligible,
            )
        scored = (ScoredItem.model_validate(dict(row)) for row in rows)
        return CandidateBatch(
            tuple(Candidate(item.item_id, item.retrieval_score) for item in scored),
            exhausted=not has_more,
        )


async def _refresh(snapshot: EmbeddingSnapshot) -> dict[str, str | int]:
    async with AsyncExitStack() as resources:
        connections = []
        for name in ("SOURCE_DATABASE_URL", "VECTOR_DATABASE_URL"):
            if not (url := os.environ.get(name)):
                raise ValueError(f"{name} is required")
            try:
                connection = await asyncpg.connect(url, timeout=5)
            except Exception as exc:
                raise RuntimeError(f"Cannot connect using {name} ({type(exc).__name__})") from None
            resources.push_async_callback(connection.close, timeout=5)
            connections.append(connection)
        source, vectors = connections
        return await refresh_index(source, vectors, snapshot)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path, help="Complete versioned JSON embedding snapshot")
    args = parser.parse_args()
    snapshot = EmbeddingSnapshot.model_validate_json(args.snapshot.read_bytes())
    print(json.dumps(asyncio.run(_refresh(snapshot))))


if __name__ == "__main__":
    main()
