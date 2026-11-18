import hashlib

from sqlalchemy import and_, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from .sql_catalog import embedding_index_versions


def hnsw_index_name(revision: str) -> str:
    digest = hashlib.sha256(revision.encode()).hexdigest()[:32]
    return f"event_embeddings_hnsw_{digest}"


async def find_published_revision(
    connection: AsyncConnection,
    model_id: str,
    revision: str | None = None,
) -> RowMapping | None:
    c = embedding_index_versions.c
    query = select(c.model_name, c.generated_at, c.artifact_sha256, c.dimension, c.metric).where(
        or_(c.model_id == model_id, and_(c.model_id.is_(None), c.model_name == model_id)),
    )
    if revision is not None:
        query = query.where(c.model_name == revision)
    return (
        (await connection.execute(query.order_by(c.generated_at.desc()).limit(1)))
        .mappings()
        .first()
    )
