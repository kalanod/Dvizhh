# Сервис рекомендаций

## Данные

Сервис читает `recsys_catalog` и `recsys_dismissals` из БД Backend.
В выдаче — мероприятия `PUBLISHED` / `PUBLIC`, без `deleted_at`,
с текущим или будущим проведением `SCHEDULED`.

## Расчёт

По умолчанию SQL-выдача сортируется по дате публикации. Настройки запуска
позволяют выбрать генератор HNSW и обученный ранкер.

Расчёт подключается через `RecommendationProvider` и возвращает порядок ID
и признак окончания выдачи. Пагинация не зависит от алгоритма.

## Two-Tower и HNSW

Типы векторов, метаданных и результатов поиска определены
в [retrieval.py](../src/dvizh_recommendation/retrieval.py).

| Тип | Данные |
| --- | --- |
| `EmbeddingSpace` | Версия модели `model_id`, размерность `dimension`, метрика `metric`. |
| `Embedding` | Описание пространства `space` и координаты вектора `values`. |
| `IndexedItem` | `item_id`, `embedding` и метаданные из схемы `event_embeddings`. |
| `ScoredItem` | `item_id`, `retrieval_score`. |

`model_id` обозначает версию модели и подготовки признаков.
Векторы и индекс должны совпадать по версии, размерности и метрике.
Результат поиска — уникальные айтемы по убыванию `retrieval_score`.
Оценка остаётся внутри сервиса и может использоваться как признак ранкера.
`limit` задаёт число найденных айтемов, `page_size` — размер страницы выдачи.

Команды из каталога `recommendation-service` выгружают историю подтверждённых
записей, обучают Two-Tower, сохраняют версию в MLflow и считают векторы пакетами.
Для обучения используются только записи пользователя, сделанные до целевой
записи. Текст и темы мероприятий берутся из каталога на момент выгрузки.

```shell
uv run python -m dvizh_recommendation.encoder_data retrieval.json \
  --history-start "$HISTORY_START" --as-of "$TRAIN_AS_OF"
uv run --group encoder python -m dvizh_recommendation.encoder_training retrieval.json \
  --validation-start "$VALIDATION_START" --experiment dvizh-retrieval \
  --model dvizh-two-tower --git-sha "$(git rev-parse HEAD)"
uv run --group encoder python -m dvizh_recommendation.generate_embeddings \
  "$MODEL_URI" embeddings.json --history-start "$HISTORY_START" --as-of "$INDEX_AS_OF"
```

`MODEL_URI` — точный `models:/имя/версия` из команды обучения. Выгрузке нужны
`SOURCE_DATABASE_URL`, обучению и генерации — `MLFLOW_TRACKING_URI`.
PyTorch используется только в командах обучения и генерации векторов.

## pgvector

Данные `IndexedItem` соответствуют схеме `event_embeddings`
из [PR #15](https://github.com/kalanod/Dvizhh/pull/15):
`item_id` соответствует `event_id`. `model_name` хранит ключ публикации,
а `embedding_index_versions.model_id` — идентификатор модели энкодера.
В этой схеме заданы 384 координаты и cosine; при выборе модели они должны совпадать
с размерностью векторов и метрикой поиска.

Индекс обновляется из снимка векторов энкодера:

```shell
uv run python -m dvizh_recommendation.vector_index embeddings.json
```

Снимок содержит `space` с `model_id`, `dimension` 384 и `metric` `cosine`,
`generated_at`, массив `items` с `item_id`, `content_hash` и `values`, массив
`users` с `user_id` и `values`. Хэш вычисляет `catalog_content_hash`.
Команда публикации возвращает ключ неизменяемого набора в поле `revision`.
Для выкладки задайте `VECTOR_MODEL_ID` и точный `VECTOR_INDEX_REVISION` из вывода
команды публикации. Без явно заданной ревизии RecSys при запуске выбирает
последнюю публикацию энкодера для новых сессий.
Продолжение использует исходную публикацию, в том числе после перезапуска.
Если есть подходящие мероприятия, но в наборе нет вектора пользователя,
RecSys возвращает `FAILED_PRECONDITION` с метаданными `recsys-reason=no-user-vector`.
Backend использует свою резервную выдачу.

## gRPC

Метод: [RecommendationService.GetRecommendations](../recommendation_service.proto).

`GetRecommendations` возвращает страницу мероприятий с идентификаторами выбранных проведений.
Поддерживаемые `filters` — `q`, `tag_id`, `date_from`, `date_to`, `free_only`,
`available_only` и `viewport` с `west`, `south`, `east`, `north`.

### Запрос

| Поле | Содержание |
| --- | --- |
| `user_id` | Идентификатор пользователя. |
| `session_id` | Идентификатор рекомендательной выдачи. |
| `request_id` | Идентификатор запроса, связывающий выдачу с логами. |
| `context` | Параметры для расчёта рекомендаций. |
| `filters` | Ограничения выдачи, применяемые сервисом рекомендаций. |
| `page_size` | Запрашиваемое число айтемов. |
| `page_token` | Токен продолжения выдачи. |

Три ID обязательны. `context` и `filters` — map с произвольными JSON-совместимыми
значениями; ключи не фиксируются в proto.

### Ответ

| Поле | Содержание |
| --- | --- |
| `items` | Упорядоченный список пар `item_id` (`events.id`) и `occurrence_id` (`event_occurrences.id`). У сохранённых ранее элементов без снимка `occurrence_id` отсутствует. |
| `next_page_token` | Токен следующей страницы; отсутствие означает конец выдачи. |

Backend загружает карточки по ID выбранных проведений и сохраняет порядок выдачи.

В режиме «Рекомендуем» Backend вызывает RecSys для авторизованного пользователя.
Адрес и таймаут задаются через `RECOMMENDATION_GRPC_ADDRESS` и
`RECOMMENDATION_GRPC_TIMEOUT_SECONDS`. При недоступности RecSys или отсутствии
вектора Backend продолжает ленту по новизне с теми же фильтрами, исключая уже
выданные карточки. Этот порядок сохраняется до обновления ленты.

## Пагинация

1. Для новой выдачи Backend создаёт `session_id` и отправляет запрос без
   `page_token`. Сервис сохраняет в Redis порядок первых 100 айтемов или всех
   найденных, если их меньше. Повтор первого запроса читает ту же выдачу.
2. Следующая страница запрашивается с тем же `session_id` и токеном из предыдущего
   ответа. `user_id`, `context` и `filters` остаются прежними.
   `page_size` — от 1 до 100, по умолчанию 20.
3. Когда сохранённого списка недостаточно, сервис рассчитывает следующую порцию,
   исключая уже сохранённые ID. Страница, пересекающая границу порций,
   возвращается после пополнения или подтверждения конца выдачи.
4. Повтор с тем же токеном и `page_size` читает те же позиции в сохранённом порядке.
   Перед ответом сервис проверяет в БД Backend именно те проведения, которые были
   выбраны при расчёте. Недоступные исключаются без замены и изменения токена.
   Страница может стать короче или пустой. Конец выдачи определяется отсутствием
   `next_page_token`.
   Одновременные запросы не добавляют одну порцию дважды.
5. Обновление ленты или смена фильтров создаёт новую сессию.
   Завершённая выдача не пополняется; новые мероприятия доступны в новой сессии.

Все экземпляры сервиса рекомендаций используют общий Redis.
Пагинация получает готовый порядок и явный признак окончания от расчёта
рекомендаций. Число результатов отдельного генератора не определяет конец выдачи.
Проверка доступности выполняется одним запросом по ID запрошенной страницы.
Уже показанные карточки автоматически не обновляются.

Срок хранения сессии — 30 минут.
`RefreshSession(user_id, session_id)` продлевает существующую сессию без расчёта
рекомендаций. Backend вызывает его по [запросу открытой ленты](../../backend/docs/DISCOVERY_CONTRACT.md)
примерно каждые 5 минут. Чтение страницы тоже продлевает срок хранения.

## Логи

| Лог | Данные |
| --- | --- |
| Выдача | RecSys сохраняет в `recommendation_pages` исходные идентификаторы, порядок и признаки использованного расчёта. |
| Взаимодействие | `user_id`, `item_id`, `event_type`, `timestamp`, `session_id` и `request_id` исходной выдачи. |

Клиентские `event_type` определены в [контракте взаимодействий](../../backend/docs/interactions.md).

`request_id` обозначает один ответ. Для событий обучения идентификаторы запроса,
сессии и пользователя передаются в формате UUID.
Backend возвращает `session_id` и `request_id` с рекомендательной страницей.
Frontend сохраняет их с карточками для отчёта о показе и записи на мероприятие.
Если при повторе запроса доступность карточек изменила страницу, RecSys возвращает
`ABORTED`. Backend повторяет запрос с прежним `page_token` и новым `request_id`.
Повтор запроса с прежним `request_id` и другим `page_size` возвращает `INVALID_ARGUMENT`.

## Обучение

Из каталога `recommendation-service` выгрузить фиксированный датасет и обучить ранкер:

```shell
uv run python -m dvizh_recommendation.dataset ./dataset \
  --start "$START" --validation-start "$VALIDATION_START" \
  --test-start "$TEST_START" --as-of "$AS_OF" \
  --observation-hours "$OBSERVATION_HOURS" --feature-version catalog-v1
uv run --group train python -m dvizh_recommendation.train ./dataset \
  --experiment dvizh --model dvizh-ranker --git-sha "$(git rev-parse HEAD)"
```

Временные границы задаются в ISO 8601 с часовым поясом. Команда обучения использует
`MLFLOW_TRACKING_URI`, записывает метрики и печатает точный `models:/имя/версия`.
При запуске команды на хосте укажите доступный с хоста адрес MLflow.
Параметры обучения передаются в `--config` как JSON.

## Выкладка модели

Укажите `MLFLOW_TRACKING_URI` и, при включённой авторизации, `MLFLOW_TRACKING_USERNAME`
и `MLFLOW_TRACKING_PASSWORD`. Для обновления работающего RecSys подготовьте
точную версию в Docker volume и переключите сервис после успешной проверки:

```shell
model_uri=models:/dvizh-ranker/3
docker compose run --rm --build prepare-ranker "$model_uri" &&
  RANKER_MODEL_URI="$model_uri" docker compose up -d --build --no-deps recommendation-service
```

Сохраните выбранный `RANKER_MODEL_URI` в окружении сервиса для следующих выкладок.
RecSys при запуске читает локальный файл. Для продолжения активных сессий можно
указать `PREVIOUS_RANKER_MODEL_URI`, `PREVIOUS_VECTOR_MODEL_ID` и
`PREVIOUS_VECTOR_INDEX_REVISION`. Предыдущая версия ранкера также должна быть
подготовлена в этом volume.
При обновлении нескольких экземпляров сначала обновите код на всех экземплярах, затем
смените версию модели и индекса. [Запуск MLflow](../../mlflow/docs/README.md).

## Запуск

Сервису нужны PostgreSQL, pgvector и Redis:

| Переменная | Назначение / значение по умолчанию |
| --- | --- |
| `SOURCE_DATABASE_URL` | Обязательный адрес БД Backend; пользователь имеет только права чтения. |
| `VECTOR_DATABASE_URL` | Обязательный адрес pgvector с правами чтения и записи. |
| `REDIS_URL` | Обязательный адрес Redis с состоянием сессий. |
| `REDIS_TIMEOUT_SECONDS` | Таймаут подключения и операции Redis; 5 секунд. |
| `RECOMMENDATION_TIMEOUT_SECONDS` | Таймаут получения страницы, включая пополнение; 5 секунд. |
| `DATABASE_POOL_MIN_SIZE` | Минимум открытых соединений с каждой БД; 1. |
| `DATABASE_POOL_MAX_SIZE` | Максимум соединений с каждой БД; 10. |
| `DATABASE_TIMEOUT_SECONDS` | Таймаут подключения, получения соединения, SQL-запроса и закрытия пула; 5 секунд. |

Адреса БД задаются в формате `postgresql://`, Redis — `redis://` или `rediss://`.
В Compose они передаются автоматически. Redis доступен только внутри сети Compose;
данные сохраняются в отдельном volume с AOF.
`database-init` подготавливает роль `recsys_reader` в основной БД.
`pgvector-init` применяет схему векторной БД, включая существующие volumes.
Для всего проекта используйте `docker compose up --build` из корня. Команда
`docker compose up --build nginx` запускает сайт со своими зависимостями.
Миграции Backend создают представления, из которых RecSys читает каталог.
При старте gRPC и далее каждые 5 секунд проверяются доступность этих представлений,
журнала `recommendation_pages` и ответ Redis на `PING`. Если проверка не проходит,
gRPC health выдаёт `NOT_SERVING` и возвращается к `SERVING` после восстановления.
При остановке сначала завершаются gRPC-запросы, затем закрываются соединения.

Из каталога `recommendation-service`:

```bash
uv sync --locked
uv run python -m dvizh_recommendation.main
```

`GRPC_BIND_ADDRESS` — адрес сервера, по умолчанию `0.0.0.0:8001`.
`SHUTDOWN_GRACE_SECONDS` — время завершения активных запросов при остановке,
по умолчанию 5 секунд.

Проверка здоровья и тесты:

```bash
uv run python -m dvizh_recommendation.healthcheck
uv run pytest
```

Интеграционные тесты требуют отдельных тестовых БД: PostgreSQL со схемой из миграций
Backend и пользователем `recsys_reader`, pgvector — с текущим `init.sql`.
Для тестов пагинации также нужен отдельный тестовый Redis.
Задать `TEST_SOURCE_DATABASE_URL`, `TEST_SOURCE_ADMIN_DATABASE_URL`,
`TEST_VECTOR_DATABASE_URL` и `TEST_REDIS_URL`, затем выполнить `uv run pytest -m integration`.
Без этих переменных интеграционные тесты пропускаются. Рабочие БД для них не использовать.

После изменения proto обновить Python-код Backend и RecSys:

```bash
uv run python generate_proto.py
uv run python generate_proto.py --check
```
