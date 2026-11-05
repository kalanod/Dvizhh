CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id          uuid PRIMARY KEY,                  -- events.id из Backend (item_id в контракте), без FK
    embedding         vector(384) NOT NULL,              -- вектор события, по нему ищет HNSW
    model_name        text NOT NULL,                     -- чем и как посчитан вектор (не смешивать модели)
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
    topic_ids         uuid[] NOT NULL DEFAULT '{}'       -- темы события (фильтр и признак ранкера)
);

CREATE INDEX IF NOT EXISTS event_embeddings_hnsw         -- поиск похожих событий по вектору (cosine)
    ON event_embeddings USING hnsw (embedding vector_cosine_ops)
    WHERE is_candidate;                                  -- только кандидаты, индекс меньше и быстрее
CREATE INDEX IF NOT EXISTS event_embeddings_dates_idx    -- быстрый фильтр по дате окончания
    ON event_embeddings (last_ends_at) WHERE is_candidate;
CREATE INDEX IF NOT EXISTS event_embeddings_topics_gin   -- быстрый фильтр по темам (topic_ids && ARRAY[...])
    ON event_embeddings USING gin (topic_ids);




    