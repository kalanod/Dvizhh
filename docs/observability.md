# Технические логи

Задать `GRAFANA_ADMIN_PASSWORD` в окружении или локальном `.env`.
Пароль применяется при первом запуске Grafana.

```shell
docker compose -f compose.yaml -f compose.logs.yaml up -d --build
```

Панель «Логи Dvizhh» открывается на `http://127.0.0.1:3000`. Начальный
пользователь — `admin`. Для разбора запроса вставить значение `X-Request-ID`
из ответа в поиск. Формат `request_id:<ID>` выбирает записи по точному ID.
Строка ошибки показывает операцию, причину и место в коде, когда они доступны.
Ссылка «Открыть trace» в деталях показывает дерево вызовов и длительность шагов.
Для 5% обычных успешных запросов сохраняются итоговая строка и trace.
Логи и trace сбоев и запросов от 1 секунды сохраняются вне этой выборки.
Trace обычно появляется через несколько секунд после завершения запроса.
Логи в Loki и trace в Tempo хранятся 14 дней.

Для `POST /api/events/discovery` trace связывает HTTP-запрос Backend и gRPC-вызов
`GetRecommendations`. `request_id` — значение `X-Request-ID` из ответа сайта.
`recommendation_request_id` — идентификатор страницы RecSys, а `session_id` —
идентификатор ленты.

Для чтения агентом задать `GRAFANA_TOKEN` от служебной учётной записи Grafana
с правами просмотра. При удалённом доступе указать HTTPS-адрес в `GRAFANA_URL`.

```shell
python3 observability/request_trace.py <request_id>
```

Команда выводит JSON с ошибками, записями и полем `trace`. `--hours` задаёт период
поиска в часах, по умолчанию один час.

### На сервере

В используемом на сервере env-файле добавить
`compose.logs.yaml:compose.logs.prod.yaml` в конец `COMPOSE_FILE`. Если переменная
ещё не задана, её значение начинается с `compose.yaml:`. Задать `GRAFANA_ADMIN_PASSWORD` и
`OBSERVABILITY_DATA_DIR=/srv/dvizh-observability` на отдельной файловой системе.
Проверить свободное место через `df -h /srv/dvizh-observability`.
При заполнении раздела на 90% Loki перестаёт принимать новые записи.

Подставить путь к серверному env-файлу вместо `.env.production`.

```shell
mountpoint -q /srv/dvizh-observability &&
  sudo install -d -m 0750 -o 10001 -g 10001 /srv/dvizh-observability/{loki,tempo} &&
  docker compose --env-file .env.production up -d --build --wait
```

Grafana доступна через SSH-туннель `ssh -N -L 3000:127.0.0.1:3000 <сервер>`.
После запуска проверить поиск по `X-Request-ID` известного запроса с ошибкой
и открыть его trace.
