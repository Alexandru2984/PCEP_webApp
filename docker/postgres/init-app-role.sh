#!/usr/bin/env bash
set -Eeuo pipefail

: "${PCEP_APP_DB:?PCEP_APP_DB is required}"
: "${PCEP_APP_USER:?PCEP_APP_USER is required}"
: "${PCEP_APP_PASSWORD:?PCEP_APP_PASSWORD is required}"

if [[ "$PCEP_APP_DB" != "$POSTGRES_DB" ]]; then
  echo "PCEP_APP_DB must match POSTGRES_DB." >&2
  exit 1
fi
if [[ "$PCEP_APP_USER" == "$POSTGRES_USER" ]]; then
  echo "The application and PostgreSQL administrator roles must differ." >&2
  exit 1
fi

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --no-password \
  --set=ON_ERROR_STOP=1 \
  --set=app_user="$PCEP_APP_USER" \
  --set=app_password="$PCEP_APP_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_user',
  :'app_password'
) \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', current_database(), :'app_user') \gexec
SQL
