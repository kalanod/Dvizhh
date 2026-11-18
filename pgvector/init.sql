CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id          uuid NOT NULL,                     -- events.id из Backend (item_id в контракте), без FK
    embedding         vector(384) NOT NULL,              -- вектор события, по нему ищет HNSW
    model_name        text NOT NULL,                     -- ключ опубликованного набора векторов
    content_hash      text NOT NULL,                     -- хэш текста события, если не изменился - не пересчитываем
    is_candidate      boolean NOT NULL,                  -- участвует в выдаче: PUBLISHED + PUBLIC + не удалено + не прошло
    source_updated_at timestamptz NOT NULL,              -- updated_at события в Backend, чтобы понять, что оно изменилось
    last_ends_at      timestamptz,                       -- конец последнего будущего occurrence (фильтр "ещё не закончилось")
    next_starts_at    timestamptz,                       -- начало ближайшего occurrence (фильтр по дате)
    price_type        text,                              -- FREE / PAID (фильтр бесплатно/платно)
    format            text,                              -- OFFLINE / ONLINE / HYBRID
    city              text,                              -- город (фильтр по городу)
    latitude          double precision,                  -- координаты для фильтра по расстоянию (у онлайн NULL)
    longitude         double precision,
    topic_ids         uuid[] NOT NULL DEFAULT '{}',      -- темы события (фильтр и признак ранкера)
    PRIMARY KEY (model_name, event_id)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.event_embeddings'::regclass
          AND contype = 'p' AND cardinality(conkey) = 1
    ) THEN
        ALTER TABLE public.event_embeddings
            DROP CONSTRAINT event_embeddings_pkey,
            ADD PRIMARY KEY (model_name, event_id);
    END IF;
END $$;

DROP INDEX IF EXISTS public.event_embeddings_hnsw;

CREATE INDEX IF NOT EXISTS event_embeddings_dates_idx    -- быстрый фильтр по дате окончания
    ON event_embeddings (last_ends_at) WHERE is_candidate;
CREATE INDEX IF NOT EXISTS event_embeddings_topics_gin   -- быстрый фильтр по темам (topic_ids && ARRAY[...])
    ON event_embeddings USING gin (topic_ids);

CREATE TABLE IF NOT EXISTS embedding_index_versions (
    model_name text PRIMARY KEY,
    model_id text,
    generated_at timestamptz NOT NULL,
    artifact_sha256 text NOT NULL,
    dimension integer NOT NULL CHECK (dimension = 384),
    metric text NOT NULL CHECK (metric = 'cosine')
);

ALTER TABLE embedding_index_versions ADD COLUMN IF NOT EXISTS model_id text;
CREATE INDEX IF NOT EXISTS embedding_index_versions_model_idx
    ON embedding_index_versions (model_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS user_embeddings (
    model_name text NOT NULL REFERENCES embedding_index_versions(model_name),
    user_id uuid NOT NULL,
    embedding vector(384) NOT NULL,
    PRIMARY KEY (model_name, user_id)
);

CREATE TABLE IF NOT EXISTS recommendation_pages (
    request_id text PRIMARY KEY,
    session_id text NOT NULL,
    user_id text NOT NULL,
    parameters_hash text NOT NULL,
    served_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    items jsonb NOT NULL CHECK (jsonb_typeof(items) = 'array')
);

CREATE INDEX IF NOT EXISTS recommendation_pages_served_idx
    ON recommendation_pages (served_at, request_id);
