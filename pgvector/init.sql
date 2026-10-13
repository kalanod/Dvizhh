CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id          uuid PRIMARY KEY,            -- = events.id
    embedding         vector(384) NOT NULL,
    model_name        text NOT NULL,               -- какой моделью посчитан
    content_hash      text NOT NULL,               -- хэш текста, чтобы не пересчитывать зря
    is_candidate      boolean NOT NULL,            -- PUBLISHED + PUBLIC + не удалено
    last_ends_at      timestamptz,                 -- конец последнего будущего occurrence
    next_starts_at    timestamptz,                 -- начало ближайшего occurrence
    price_type        text,                        -- FREE / PAID
    format            text,                        -- OFFLINE / ONLINE / HYBRID
    city              text,
    latitude          double precision,
    longitude         double precision,
    topic_ids         uuid[] NOT NULL DEFAULT '{}',
    source_updated_at timestamptz NOT NULL,        -- events.updated_at на момент индексации
    indexed_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS event_embeddings_hnsw
    ON event_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS event_embeddings_candidate_idx
    ON event_embeddings (is_candidate, last_ends_at);
CREATE INDEX IF NOT EXISTS event_embeddings_topics_gin
    ON event_embeddings USING gin (topic_ids);

-- до какого момента индексатор уже прочитал events
CREATE TABLE IF NOT EXISTS indexer_state (
    name       text PRIMARY KEY,
    watermark  timestamptz NOT NULL DEFAULT 'epoch'
);