# pgvector

Отдельный PostgreSQL с расширением [pgvector](https://github.com/pgvector/pgvector). Хранит эмбеддинги событий и позволяет быстро находить события, близкие по смыслу к интересам пользователя. На этом строится персональная выдача афиши.

## Назначение и границы

Эмбеддинг превращает текст события в вектор из 384 чисел: близкие по смыслу события получают близкие векторы. Это позволяет искать похожие события без ручных категорий.

- Основная БД `postgres` остаётся источником истины. В `pgvector` лежат только производные данные, которые можно пересчитать.
- Связь с `postgres` идёт по `event_id` (внешних ключей между базами нет).
- Писать в `pgvector` может только `recommendation-service`.
- Тексты карточек, пользователи и история действий здесь не хранятся.

| Входит | Не входит |
|---|---|
| Образ, запуск и настройка БД | Расчёт эмбеддингов (`recommendation-service`) |
| Схема таблиц и индексы | Итоговое ранжирование ленты (`recommendation-service`) |
| Допустимые запросы | Карточки и тексты событий (`postgres`) |

## Место в архитектуре

```mermaid
flowchart LR
    B[backend] --> R[recommendation-service]
    B --> PG[(postgres)]
    R --> V[(pgvector)]
    R -.->|чтение| PG
```

Порт `pgvector` наружу не публикуется, база доступна только внутри сети docker compose.

![BPMN индексации и выдачи](BPMN.png)

## Структура каталога

```
pgvector/
├── Dockerfile      # образ на базе pgvector/pgvector
├── .dockerignore
├── init.sql        # расширение, таблицы и индексы
└── README.md
```

`init.sql` выполняется только при первом запуске с пустым volume. Чтобы применить изменения схемы, нужно пересоздать volume (см. «Сброс базы»).

## Быстрый старт

```shell
docker compose up -d --build pgvector
docker compose ps pgvector          # статус должен быть healthy
```

Проверка, что расширение и таблица созданы:

```shell
docker compose exec pgvector psql -U dvizh -d dvizh_vectors -c "\dx"
docker compose exec pgvector psql -U dvizh -d dvizh_vectors -c "\d event_embeddings"
```

В списке расширений должен быть `vector`.

## Конфигурация

Переменные из `.env` (значения по умолчанию заданы в `compose.yaml`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `VECTOR_DB` | `dvizh_vectors` | имя базы |
| `VECTOR_USER` | `dvizh` | пользователь |
| `VECTOR_PASSWORD` | `change-me` | пароль (замените в `.env`) |

Настройка при подключении из сервиса, чтобы фильтры не обрезали выдачу:

```sql
SET hnsw.iterative_scan = relaxed_order;
SET hnsw.ef_search = 100;
```

## Модель данных

Размерность вектора: **384** (модель `intfloat/multilingual-e5-small`). При смене модели таблицу нужно пересоздать.

### `event_embeddings`

Одна строка на событие (не на каждый сеанс), чтобы повторяющееся событие не занимало ленту копиями.

| Поле | Откуда в `postgres` | Зачем |
|---|---|---|
| `event_id` (PK, uuid) | `events.id` | связь с основной БД |
| `embedding` | считается из текста события | поиск по смыслу |
| `model_name`, `content_hash` | служебные | пересчитывать вектор только при изменении текста или модели |
| `is_candidate` | `status = PUBLISHED`, `visibility = PUBLIC`, не удалено | попадает ли событие в поиск |
| `next_starts_at`, `last_ends_at` | `event_occurrences` | фильтр по времени |
| `price_type`, `format` | `events` | фильтры |
| `city`, `latitude`, `longitude` | `locations` | география |
| `topic_ids` | `event_topics` | фильтр по тематикам |
| `source_updated_at` | `events.updated_at` | не принять устаревшее обновление поверх свежего |
| `indexed_at` | служебное | когда строка была записана |

### `indexer_state`

Служебная таблица: до какого момента (`watermark`) индексатор уже прочитал `events`.

### Что в `pgvector` не хранится

- названия, описания и другие тексты карточек;
- персональные данные и история действий пользователей;
- быстро меняющиеся счётчики (сколько идёт, сколько сохранили);
- неопубликованные, приватные и удалённые события (`is_candidate = false`, либо строки нет).

## Индексы

| Индекс | Тип | Для чего |
|---|---|---|
| `event_embeddings_hnsw` | HNSW по `embedding`, косинусное расстояние | поиск ближайших событий |
| `event_embeddings_candidate_idx` | B-tree `(is_candidate, last_ends_at)` | отбор актуальных кандидатов |
| `event_embeddings_topics_gin` | GIN по `topic_ids` | фильтр по тематикам |

HNSW ищет приближённо: быстрее полного перебора, но может изредка пропустить подходящий результат. При небольшом числе событий (до нескольких тысяч) точный перебор тоже достаточно быстр.

## Эмбеддинги

| Параметр | Значение |
|---|---|
| Модель | `intfloat/multilingual-e5-small` |
| Размерность | 384 |
| Метрика | косинусное расстояние (`<=>`), векторы нормализованы |
| Кто считает | `recommendation-service` |

Текст события для вектора начинается с `passage: `, поисковый запрос с `query: ` (особенность моделей E5). Даты, цена и вместимость в текст не входят: это поля-фильтры.

## Контракт запросов

Параметры подставляет `recommendation-service`.

**Кандидаты** (`$1` вектор пользователя или запроса):

```sql
SELECT event_id, 1 - (embedding <=> $1) AS similarity
FROM event_embeddings
WHERE is_candidate
  AND last_ends_at > now()
ORDER BY embedding <=> $1
LIMIT 200;
```

**Добавление или обновление** (повтор безопасен, устаревшее обновление не затирает свежее):

```sql
INSERT INTO event_embeddings
    (event_id, embedding, model_name, content_hash, is_candidate,
     next_starts_at, last_ends_at, source_updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (event_id) DO UPDATE SET
    embedding         = EXCLUDED.embedding,
    model_name        = EXCLUDED.model_name,
    content_hash      = EXCLUDED.content_hash,
    is_candidate      = EXCLUDED.is_candidate,
    next_starts_at    = EXCLUDED.next_starts_at,
    last_ends_at      = EXCLUDED.last_ends_at,
    source_updated_at = EXCLUDED.source_updated_at,
    indexed_at        = now()
WHERE event_embeddings.source_updated_at <= EXCLUDED.source_updated_at;
```

**Удаление** отменённого или удалённого события:

```sql
DELETE FROM event_embeddings WHERE event_id = $1;
```

## Быстрая проверка

Данные из `postgres` для этого не нужны.

### 1. Проверка за минуту (без модели)

Три события с вручную заданными векторами. Всё выполняется в транзакции и откатывается, таблица остаётся пустой.

```shell
docker compose exec -T pgvector psql -U dvizh -d dvizh_vectors <<'SQL'
BEGIN;

-- вектор из первых координат, остальные нули (всего 384)
CREATE FUNCTION pg_temp.v(head float8[]) RETURNS vector AS $$
  SELECT array_cat(head, array_fill(0::float8, ARRAY[384 - cardinality(head)]))::vector
$$ LANGUAGE sql;

INSERT INTO event_embeddings
    (event_id, embedding, model_name, content_hash, is_candidate, last_ends_at, source_updated_at)
VALUES
    ('00000000-0000-0000-0000-000000000001', pg_temp.v('{1,0.1}'), 'test', 'x', true,  now() + interval '7 days', now()),
    ('00000000-0000-0000-0000-000000000002', pg_temp.v('{0,1}'),   'test', 'x', true,  now() + interval '7 days', now()),
    ('00000000-0000-0000-0000-000000000003', pg_temp.v('{1,0}'),   'test', 'x', false, now() + interval '7 days', now());

SELECT event_id, round((1 - (embedding <=> pg_temp.v('{1,0}')))::numeric, 3) AS similarity
FROM event_embeddings
WHERE is_candidate AND last_ends_at > now()
ORDER BY embedding <=> pg_temp.v('{1,0}')
LIMIT 3;

ROLLBACK;
SQL
```

Ожидаемый результат: две строки, первой идёт `...0001` (similarity около 0.995), второй `...0002` (0.000). Событие `...0003` не попало в выдачу, потому что `is_candidate = false`.

### 2. Проверка с настоящей моделью

Нужен доступ к базе с вашей машины: временно добавьте в сервис `pgvector` в `compose.yaml`

```yaml
    ports:
      - "5433:5432"
```

и перезапустите `docker compose up -d pgvector`. После проверки уберите эти строки.

Зависимости ставятся в локальный venv (в кавычках, иначе zsh воспримет `[binary]` как шаблон):

```shell
python3 -m venv .venv && source .venv/bin/activate
pip install "psycopg[binary]" pgvector sentence-transformers
```

Скрипт `seed_demo.py` записывает в базу демо-события с настоящими векторами и выводит ближайших для двух запросов:

```shell
PGVECTOR_DSN="postgresql://dvizh:change-me@localhost:5433/dvizh_vectors" python seed_demo.py
```

Признак успеха: на запрос «хочу сыграть в падел» первым выходит событие про теннис, на «что-нибудь послушать вечером» событие про джаз-оркестр.

### 3. Автотесты

Тесты на базу лежат в `recommendation-service/tests/test_pgvector.py`. Без переменной `PGVECTOR_DSN` они пропускаются, поэтому остальные тесты не ломаются.

```shell
cd recommendation-service
PGVECTOR_DSN="postgresql://dvizh:change-me@localhost:5433/dvizh_vectors" uv run pytest tests/test_pgvector.py -v
```

Тесты очищают `event_embeddings`, поэтому запускайте их только на локальной базе.

## Сброс базы

Данные можно пересчитать из `postgres`. Чтобы пересоздать базу и заново выполнить `init.sql`:

```shell
docker compose rm -sf pgvector
docker volume rm dvizh_pgvector-data
docker compose up -d --build pgvector
```

## Типичные проблемы

| Симптом | Причина и решение |
|---|---|
| `no pq wrapper available` | Установлен `psycopg` без бинарной части: `pip install "psycopg[binary]"`. |
| Изменил `init.sql`, ничего не поменялось | Скрипт выполняется только на пустом volume: см. «Сброс базы». |
| `different vector dimensions` | Размерность вектора не равна 384: проверьте модель и колонку. |
| Подключение с машины отказывает | Порт не опубликован: временно добавьте `5433:5432` (см. выше). |