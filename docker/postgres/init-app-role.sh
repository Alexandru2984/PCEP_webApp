#!/usr/bin/env bash
set -Eeuo pipefail

: "${PCEP_APP_DB:?PCEP_APP_DB is required}"
: "${PCEP_APP_USER:?PCEP_APP_USER is required}"
: "${PCEP_APP_PASSWORD:?PCEP_APP_PASSWORD is required}"
: "${PCEP_OWNER_ROLE:?PCEP_OWNER_ROLE is required}"
: "${PCEP_MIGRATOR_USER:?PCEP_MIGRATOR_USER is required}"

if [[ "$PCEP_APP_DB" != "$POSTGRES_DB" ]]; then
  echo "PCEP_APP_DB must match POSTGRES_DB." >&2
  exit 1
fi
if [[ "$PCEP_APP_USER" == "$POSTGRES_USER" ]]; then
  echo "The application and PostgreSQL administrator roles must differ." >&2
  exit 1
fi
if [[ "$PCEP_OWNER_ROLE" == "$POSTGRES_USER" || "$PCEP_MIGRATOR_USER" == "$POSTGRES_USER" ]]; then
  echo "The owner, migrator and PostgreSQL administrator roles must differ." >&2
  exit 1
fi
if [[ "$PCEP_APP_USER" == "$PCEP_OWNER_ROLE" || "$PCEP_APP_USER" == "$PCEP_MIGRATOR_USER" || "$PCEP_OWNER_ROLE" == "$PCEP_MIGRATOR_USER" ]]; then
  echo "The application, owner and migrator roles must be distinct." >&2
  exit 1
fi

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --no-password \
  --set=ON_ERROR_STOP=1 \
  --set=app_user="$PCEP_APP_USER" \
  --set=app_password="$PCEP_APP_PASSWORD" \
  --set=owner_role="$PCEP_OWNER_ROLE" \
  --set=migrator_user="$PCEP_MIGRATOR_USER" <<'SQL'
SELECT format(
  'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'owner_role'
) \gexec
SELECT format(
  'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'migrator_user'
) \gexec
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_user',
  :'app_password'
) \gexec
SELECT format('GRANT %I TO %I', :'owner_role', :'migrator_user') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', current_database(), :'owner_role') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'migrator_user') \gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', :'owner_role') \gexec
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
  :'owner_role',
  :'app_user'
) \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
  :'owner_role',
  :'app_user'
) \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC',
  :'owner_role'
) \gexec
SQL
