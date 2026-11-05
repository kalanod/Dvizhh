#!/bin/sh
set -eu

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${VECTOR_USER:?VECTOR_USER is required}"
: "${VECTOR_PASSWORD:?VECTOR_PASSWORD is required}"
: "${VECTOR_DB:?VECTOR_DB is required}"

export PGHOST=postgres PGPORT=5432 PGCONNECT_TIMEOUT=10
export PGPASSWORD="$POSTGRES_PASSWORD"
echo "Preparing recommendation reader permissions..."
sh /opt/dvizh/init-recsys-reader.sh

echo "Preparing vector database schema..."
PGHOST=pgvector PGPASSWORD="$VECTOR_PASSWORD" psql -X \
    --username "$VECTOR_USER" --dbname "$VECTOR_DB" \
    --set ON_ERROR_STOP=1 --single-transaction --file /opt/dvizh/vector.sql
echo "Database preparation complete."
