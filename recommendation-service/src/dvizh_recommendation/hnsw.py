from collections.abc import Sequence
from uuid import UUID

import asyncpg

from .index_revision import find_published_revision, hnsw_index_name
from .recommendations import Candidate, CandidateBatch, NoUserVector, RecommendationQuery
from .retrieval import ScoredItem


class HnswCandidates:
    name = "hnsw"

    def __init__(self, pool: asyncpg.Pool, model_id: str, revision: str | None = None) -> None:
        self.pool = pool
        self.model_id = model_id
        self.revision = revision

    async def check_ready(self) -> bool:
        published = await find_published_revision(self.pool, self.model_id, self.revision)
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
            f"public.{hnsw_index_name(revision)}",
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
            has_more = eligible is None or len(rows) < len(eligible)
            if has_more and len(rows) < limit:
                has_more = await connection.fetchval(
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
        scored = (ScoredItem(**row) for row in rows)
        return CandidateBatch(
            tuple(Candidate(item.item_id, item.retrieval_score) for item in scored),
            exhausted=not has_more,
        )
