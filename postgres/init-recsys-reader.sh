#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${RECSYS_READER_PASSWORD:?RECSYS_READER_PASSWORD is required}"

psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv reader_password RECSYS_READER_PASSWORD
\getenv backend_owner POSTGRES_USER
\getenv source_database POSTGRES_DB

BEGIN;
SELECT 'CREATE ROLE recsys_reader'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recsys_reader')
\gexec
ALTER ROLE recsys_reader WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE :"source_database" TO recsys_reader;
GRANT USAGE ON SCHEMA public TO recsys_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO recsys_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE :"backend_owner" IN SCHEMA public
    GRANT SELECT ON TABLES TO recsys_reader;
COMMIT;
SQL
