#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${MLFLOW_DATABASE_PASSWORD:?MLFLOW_DATABASE_PASSWORD is required}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
: "${MLFLOW_STORAGE_SECRET_KEY:?MLFLOW_STORAGE_SECRET_KEY is required}"

export PGHOST=postgres PGPORT=5432 PGCONNECT_TIMEOUT=10
export PGPASSWORD="$POSTGRES_PASSWORD"

psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv mlflow_password MLFLOW_DATABASE_PASSWORD

SELECT 'CREATE ROLE mlflow'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mlflow')
\gexec
ALTER ROLE mlflow WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'mlflow_password';

SELECT 'CREATE DATABASE mlflow OWNER mlflow'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mlflow')
\gexec
ALTER DATABASE mlflow OWNER TO mlflow;
SQL

if ! printf '%s\n%s\n' "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" |
    mc alias set storage http://minio:9000 >/dev/null 2>&1; then
    echo "Cannot configure MLflow storage access." >&2
    exit 1
fi

mc mb --ignore-existing storage/mlflow-artifacts
printf '%s\n' "$MLFLOW_STORAGE_SECRET_KEY" | mc admin user add storage mlflow
mc admin policy create storage mlflow-artifacts /opt/dvizh/policy.json
mc admin policy attach storage mlflow-artifacts --user mlflow
