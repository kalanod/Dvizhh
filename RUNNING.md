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
