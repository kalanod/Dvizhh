#!/bin/sh
set -eu

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

export PGHOST=postgres PGPORT=5432 PGCONNECT_TIMEOUT=10
export PGPASSWORD="$POSTGRES_PASSWORD"
echo "Preparing recommendation reader permissions..."
sh /opt/dvizh/init-recsys-reader.sh

echo "Preparing authentication database..."
psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE DATABASE dvizh_auth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dvizh_auth')
\gexec
SQL

echo "PostgreSQL preparation complete."
