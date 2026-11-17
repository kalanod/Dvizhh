# Основной API

Действуют [корневые инструкции](../AGENTS.md). Команды ниже - из `backend`.

## Границы и структура

Пакет `src/dvizh_backend/`:
- `api/routers/` - HTTP-слой,
- `api/schemas/` - контракты,
- `api/errors.py` - перевод ошибок сервисов в HTTP-ответы,
- `services/` - прикладная логика,
- `database/models/` - SQLAlchemy-модели,
- `database/services/` - работа с данными,
- `storage.py` - файловое хранилище.

Сборка зависимостей и request-scoped транзакций находится в `api/dependencies.py`,
HTTP-защита — в `api/security.py`. Бизнес-сервисы не импортируют FastAPI и роутеры.
`main.py` создаёт приложение, управляет lifespan и подключает роутеры и обработчики
ошибок. HTTP-маршруты, включая healthcheck, объявляйте только в `api/routers/`.

Сохраняй эти границы; не переноси SQL и правила доступа в обработчики UI.
Используй существующие зависимости сессий и сервисов.

Сохраняй проверки владельца, видимости, участия и жизненного цикла мероприятий
и медиа. Изменения состояния и связанных данных должны быть согласованы в транзакции.
Проверяй ошибки, повторные запросы и недопустимые переходы.
Реальное состояние интеграции auth проверяй по коду.

## Схема и контракты

Миграции находятся в `alembic/versions/`, включая SQL в `versions/sql/`.
Для изменений схемы добавляйте новую ревизию, согласуй модели и миграции.
Проверяйте upgrade и, если предусмотрен, downgrade на одноразовой БД.
Изменения API отражайте в `docs/PERSONAL_API.md`, `docs/MEDIA_LIFECYCLE_API.md`,
`docs/interactions.md` и frontend, когда затронут соответствующий контракт.

## Команды

- Установка: `uv sync --locked`.
- Линт и тесты: `uv run ruff check .`, `uv run pytest`.
- Локальный запуск: `uv run uvicorn dvizh_backend.main:app --reload --port 8000`.
- Применение миграций к выбранной локальной БД: `uv run alembic upgrade head`.
- Media/personal-интеграция: `uv run python tests/run_integration.py`; нужны Docker
  и локальные образы `dvizh-postgres`, `dvizh-minio` (сборка из корня:
  `docker compose build postgres minio`). Подробности в `docs/MEDIA_LIFECYCLE_API.md`.

Не направляй интеграционные проверки и миграционные эксперименты на рабочую БД.
