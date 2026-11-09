# Сервис рекомендаций

Действуют [корневые инструкции](../AGENTS.md). Команды - из `recommendation-service`.

Пакет `src/dvizh_recommendation/`: `service.py` - gRPC, `candidates.py` - кандидаты,
`retrieval.py` - контракты векторного поиска, `database.py` - пулы соединений.
Источник gRPC-контракта - `recommendation_service.proto`.

Основную БД читай через роль с правами только чтения. Производные векторы
принадлежат pgvector. Не добавляй запись в основную БД из рекомендательного сервиса.
Сохраняй фильтрацию доступных публичных мероприятий, уникальность ID и
детерминированный порядок. Не описывай fallback по свежести как персонализацию.
Проверяй реализованность векторного поиска, моделей и сессионного хранения по коду:
документация также содержит проектируемые возможности.

При изменении векторных контрактов согласуй версию модели, размерность и метрику
со схемой pgvector. При изменении proto сохраняйте совместимость номеров полей.
`src/dvizh_recommendation/generated/` не редактируй вручную:

```shell
uv run python generate_proto.py
uv run python generate_proto.py --check
```

Установка: `uv sync --locked`; проверки: `uv run ruff check .`, `uv run pytest`.
Запуск: `uv run python -m dvizh_recommendation.main`;
здоровье: `uv run python -m dvizh_recommendation.healthcheck`.
Нужны `SOURCE_DATABASE_URL` и `VECTOR_DATABASE_URL`; детали в [README.md](README.md).

Интеграция: `uv run pytest -m integration` с `TEST_SOURCE_DATABASE_URL`,
`TEST_SOURCE_ADMIN_DATABASE_URL`, `TEST_VECTOR_DATABASE_URL` для отдельных тестовых БД.
Без настроек интеграционные тесты пропускаются; сообщай это в результате проверки.
