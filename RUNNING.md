# Запуск и разработка

## Запуск в Docker

1. Скопировать `.env.example` в `.env` и заменить пароли.
2. Запуск проекта из корня репозитория:

   ```shell
   docker compose up --build
   ```

3. Откройте `http://localhost:8080`.

Миграции базы применяются автоматически при старте контейнера `backend`.

Проверка API:

```shell
curl http://localhost:8080/api/health
```

Swagger основного backend: `http://localhost:8080/api/docs`.

Консоль MinIO: `http://localhost:9001`.

### Существующие БД

После обновления с версии без пользователя `recsys_reader` применить права чтения:

```shell
docker compose up -d --build postgres pgvector
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/01-recsys-reader.sh
```

На новой БД пользователь создаётся автоматически. Его пароль задаётся
через `RECSYS_READER_PASSWORD` в `.env`.

Если pgvector был инициализирован до добавления таблицы `event_embeddings`,
применить текущую схему:

```shell
docker compose exec -T pgvector sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-vector.sql'
```

После этого запустить остальные сервисы через `docker compose up --build`.
Повторное применение этих команд сохраняет данные; удалять volumes не требуется.

## Остановка

```shell
docker compose down
```

## Локальная разработка Python-сервисов

Команды выполняются из каталога нужного сервиса, например `backend`:

```shell
uv sync --locked
uv run ruff check .
uv run pytest
```

Запуск backend локально (Swagger: `http://localhost:8000/api/docs`):

```shell
uv run uvicorn dvizh_backend.main:app --reload --port 8000
```

Без PostgreSQL backend всё равно стартует и показывает Swagger, но запросы к данным
вернут 500. Таблицы создаются миграциями Alembic:

```shell
uv run alembic upgrade head
```

Добавление зависимости и обновление lock-файла:

```shell
uv add package-name
```
