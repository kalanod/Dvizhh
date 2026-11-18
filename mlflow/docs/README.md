# MLflow

Из корня репозитория запустите общие хранилища и отдельный проект MLflow:

```shell
docker compose up -d --build --wait postgres minio
docker compose -p dvizh-mlflow -f compose.mlflow.yaml up -d --build --wait
```

Локальный реестр доступен по `http://localhost:5000`, из контейнеров приложения —
по `http://mlflow:5000`. Для остановки реестра используйте
`docker compose -p dvizh-mlflow -f compose.mlflow.yaml down`. PostgreSQL и MinIO общие для приложения
и MLflow, поэтому отказ одного из хранилищ затронет оба проекта.

MLflow подключается к сети `dvizh_default`. Если у проекта приложения другое имя,
задайте фактическую сеть через `DVIZH_APP_NETWORK`.

Для Python-клиента вне сети Compose задайте `MLFLOW_ENABLE_PROXY_MULTIPART_UPLOAD=false`
и `MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false`. Файлы пройдут через MLflow, доступ
к MinIO клиенту не нужен.

## HTTPS и авторизация

На сервере используйте общий `.env.production` с реквизитами PostgreSQL и MinIO.
Для реестра задайте `MLFLOW_DOMAIN`, `MLFLOW_DATABASE_PASSWORD`,
`MLFLOW_STORAGE_SECRET_KEY`, `MLFLOW_AUTH_ADMIN_PASSWORD` и `MLFLOW_FLASK_SERVER_SECRET_KEY`.

```shell
docker compose --env-file .env.production up -d --build --wait postgres minio
docker compose --env-file .env.production -p dvizh-mlflow -f compose.mlflow.yaml \
  -f compose.mlflow.prod.yaml up -d --build --wait
```

Для остановки HTTPS-варианта передайте те же файлы и имя проекта команде `down`.

Перед первым запуском остановите `mlflow` и `mlflow-gateway` прежней конфигурацией.
Новый проект использует ту же БД `mlflow`, бакет
`mlflow-artifacts` и тома Caddy из стандартного проекта `dvizh`. Для другого имени
укажите прежние тома через `MLFLOW_CADDY_DATA_VOLUME` и `MLFLOW_CADDY_CONFIG_VOLUME`.

## Резервное копирование

Команда сохраняет БД и файлы моделей вместе в новый каталог.

```shell
python3 mlflow/backup.py --env-file .env.production backup /path/to/new-backup
```

Восстановление выполняет команда `restore` с путём к проверенной копии.
Она заменяет данные MLflow.

Если реестр запущен с нестандартным именем или конфигурацией, передайте его
`COMPOSE_PROJECT_NAME` и `COMPOSE_FILE` со списком файлов реестра.
