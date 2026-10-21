# Запуск и разработка

## Запустить весь проект

Нужен только запущенный Docker Desktop. Из корня репозитория:

```shell
docker compose up --build
```

Открыть **http://localhost:8080**. Фронтенд, backend, рекомендации и хранилища
запускаются одной командой. Node.js, npm и Python на компьютере для этого не нужны.
`.env` для локального запуска необязателен: Compose содержит значения по умолчанию.
При необходимости скопируйте `.env.example` в `.env` и измените настройки.

Compose автоматически выполняет все шаги:

1. Собирает React внутри Node-контейнера и готовит nginx со статикой.
2. Запускает PostgreSQL, pgvector и MinIO и ждёт их готовности.
3. `database-init` создаёт или обновляет роль `recsys_reader`, права чтения
   и схему pgvector. `minio-init` создаёт bucket, если его ещё нет.
4. Запускает сервис рекомендаций и backend, который применяет миграции Alembic.
5. После готовности API запускает web-app и внешний nginx.

Это работает и с новыми, и с существующими volumes. Подготовительные контейнеры
`database-init` и `minio-init` штатно заканчивают работу с кодом 0.
Ручные SQL-команды и отдельный запуск Vite не требуются.

Для запуска в фоне можно добавить `-d`:

```shell
docker compose up -d --build
```

## Адреса

| Сервис | Адрес |
| --- | --- |
| Сайт | http://localhost:8080 |
| Проверка API и БД | http://localhost:8080/api/health |
| Swagger | http://localhost:8080/api/docs |
| Консоль MinIO | http://localhost:9001 |

Порт сайта настраивается через `NGINX_PORT` в `.env`, по умолчанию `8080`.
Открывайте сайт по этому адресу; порт `5173` относится только к необязательному
режиму разработки ниже.

## Обновление и остановка

После изменений кода используйте ту же команду `docker compose up --build`:
фронтенд пересоберётся, подготовка БД и миграции выполнятся автоматически.

```shell
docker compose ps --all
docker compose logs -f
docker compose down
```

Остановка через `docker compose down` сохраняет данные в volumes.

## Вход в приложение

Зарегистрируйтесь через интерфейс. Авторизации пока нет: регистрация создаёт
профиль через `POST /api/users`, вход выполняется по ID профиля.
На новой БД заранее созданных пользователей нет.

## Необязательно: разработка фронтенда с быстрым обновлением

Обычный запуск выше уже содержит весь фронтенд. Этот режим нужен только для
изменения компонентов без пересборки Docker-образа. Для него нужен Node.js 22+.
При работающем Docker-стеке создайте `web-app/.env.development.local`:

```text
BACKEND_URL=http://127.0.0.1:8080
```

Из `web-app`:

```shell
npm ci
npm run dev
```

Адрес этого отдельного dev-сервера: http://localhost:5173.

## Проверки для разработчиков

Из `web-app`:

```shell
npm ci
npm test
npm run lint
npm run build
```

Из `backend` с Python 3.12 и uv:

```shell
uv sync --locked
uv run ruff check .
uv run pytest
.\test-media.ps1
```

`test-media.ps1` проверяет media/personal API и миграции на отдельных временных
PostgreSQL и MinIO; нужны локальные образы `dvizh-postgres` и `dvizh-minio`.

Из корня репозитория с Python 3.12+:

```shell
python database-init/tests/test_startup.py
python web-app/tests/test_proxy.py
```

Первая проверка использует отдельные PostgreSQL/pgvector и проверяет восстановление
роли, схемы и повторный запуск с сохранением тестовых данных. Нужны образы
`dvizh-postgres`, `dvizh-pgvector`, `dvizh-database-init`, собранные Compose.
Вторая собирает отдельную цепочку nginx → web-app → backend-заглушка и проверяет
SPA-маршруты, query-параметры и лимиты обычных/chunked-загрузок.
Проверки удаляют только собственные тестовые контейнеры и сети.

При локальном запуске backend без Docker команды выполняются из `backend`:

```shell
uv run alembic upgrade head
uv run uvicorn dvizh_backend.main:app --reload --port 8000
```

Добавление зависимости: `uv add package-name`.
