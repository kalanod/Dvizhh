from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, pg_catalog
from sqlalchemy.ext.asyncio import AsyncEngine

from .database import read_snapshot
from .index_revision import find_published_revision, hnsw_index_name
from .recommendations import Candidate, CandidateBatch, NoUserVector, RecommendationQuery
from .retrieval import ScoredItem
from .sql_catalog import event_embeddings, user_embeddings


class HnswCandidates:
    name = "hnsw"

    def __init__(self, pool: AsyncEngine, model_id: str, revision: str | None = None) -> None:
        self.pool = pool
        self.model_id = model_id
        self.revision = revision

    async def check_ready(self) -> bool:
        async with self.pool.connect() as connection:
            published = await find_published_revision(connection, self.model_id, self.revision)
            if (
                published is None
                or published["dimension"] != 384
                or published["metric"] != "cosine"
            ):
                return False
            revision = published["model_name"]
            index, relation, method = pg_catalog.pg_index, pg_catalog.pg_class, pg_catalog.pg_am
            valid_index = (
                sa.select(index.c.indexrelid)
                .select_from(
                    index.join(relation, relation.c.oid == index.c.indexrelid).join(
                        method, method.c.oid == relation.c.relam
                    )
                )
                .where(
                    index.c.indexrelid
                    == sa.func.to_regclass(f"public.{hnsw_index_name(revision)}"),
                    index.c.indrelid == sa.func.to_regclass("public.event_embeddings"),
                    index.c.indisvalid,
                    index.c.indisready,
                    method.c.amname == "hnsw",
                )
            )
            if not await connection.scalar(sa.select(valid_index.exists())):
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
        if viewer is None or self.revision is None:
            raise NoUserVector
        async with self.pool.connect() as connection, read_snapshot(connection):
            u = user_embeddings.c
            embedding = await connection.scalar(
                sa.select(u.embedding).where(
                    u.model_name == self.revision,
                    u.user_id == viewer,
                )
            )
            if embedding is None:
                raise NoUserVector
            await connection.execute(
                sa.select(
                    sa.func.set_config(
                        "hnsw.iterative_scan",
                        "strict_order",
                        True,
                    )
                )
            )
            c = event_embeddings.c
            revision = sa.literal(self.revision, type_=sa.Text, literal_execute=True)
            candidates = sa.select(c.event_id).where(c.is_candidate, c.model_name == revision)
            if exclude_ids:
                candidates = candidates.where(
                    c.event_id != sa.all_(sa.literal(list(exclude_ids), ARRAY(sa.Uuid)))
                )
            if eligible_ids is not None:
                candidates = candidates.where(
                    c.event_id == sa.any_(sa.literal(list(eligible_ids), ARRAY(sa.Uuid)))
                )
            distance = c.embedding.cosine_distance(embedding)
            nearest = (
                candidates.add_columns(distance.label("distance"))
                .order_by(distance)
                .limit(limit)
                .cte("nearest")
                .prefix_with("MATERIALIZED", dialect="postgresql")
            )
            result = await connection.execute(
                sa.select(
                    nearest.c.event_id.label("item_id"),
                    (1 - nearest.c.distance).label("retrieval_score"),
                ).order_by(nearest.c.distance, nearest.c.event_id)
            )
            scored = tuple(ScoredItem.model_validate(row) for row in result.mappings())
            has_more = eligible_ids is None or len(scored) < len(eligible_ids)
            if has_more and len(scored) < limit:
                remaining = candidates
                if scored:
                    remaining = remaining.where(
                        c.event_id
                        != sa.all_(sa.literal([item.item_id for item in scored], ARRAY(sa.Uuid)))
                    )
                has_more = await connection.scalar(sa.select(remaining.exists()))
        return CandidateBatch(
            tuple(Candidate(item.item_id, item.retrieval_score) for item in scored),
            exhausted=not has_more,
        )
