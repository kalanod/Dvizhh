import hashlib

import asyncpg

_PUBLISHED_INDEX = """
SELECT model_name, generated_at, artifact_sha256, dimension, metric
FROM public.embedding_index_versions
WHERE (model_id = $1 OR (model_id IS NULL AND model_name = $1))
  AND ($2::text IS NULL OR model_name = $2)
ORDER BY generated_at DESC
LIMIT 1
"""


def hnsw_index_name(revision: str) -> str:
    digest = hashlib.sha256(revision.encode()).hexdigest()[:32]
    return f"event_embeddings_hnsw_{digest}"


async def find_published_revision(
    database: asyncpg.Connection | asyncpg.Pool, model_id: str, revision: str | None = None
) -> asyncpg.Record | None:
    return await database.fetchrow(_PUBLISHED_INDEX, model_id, revision)
