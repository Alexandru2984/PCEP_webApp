#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_file="$(mktemp)"
candidate="pcep-postgres-hardening-${$}"
volume="pcep_postgres_hardening_${$}"

cleanup() {
  docker rm -f "$candidate" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  rm -f "$config_file"
}
trap cleanup EXIT

cd "$root"
docker compose --profile maintenance config --format json >"$config_file"

db_image="$(python3 - "$config_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    services = json.load(config_file)["services"]
    service = services["db"]
    migrator = services["backend-migrate"]


def require(condition, message):
    if not condition:
        raise SystemExit(f"PostgreSQL Compose hardening check failed: {message}")


expected_base = (
    "postgres:16-alpine@"
    "sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
)
require(
    service.get("image") == "pcep_webapp-postgres:16.15-alpine3.24",
    "the service must use the reviewed local image",
)
require(
    service.get("build", {}).get("args", {}).get("POSTGRES_IMAGE") == expected_base,
    "the upstream PostgreSQL image must use the reviewed digest",
)
require(service.get("user") == "postgres", "the container must start as postgres")
require(service.get("read_only") is True, "the root filesystem must be read-only")
require(service.get("cap_drop") == ["ALL"], "all Linux capabilities must be dropped")
require(
    "no-new-privileges:true" in service.get("security_opt", []),
    "no-new-privileges must be enabled",
)
require(service.get("pids_limit") == 128, "the PID limit must remain 128")
require(service.get("mem_limit") == "536870912", "the memory limit must remain 512 MiB")
require(not service.get("ports"), "PostgreSQL must not publish a host port")
require(service.get("stop_grace_period") == "1m0s", "graceful shutdown must get 60 seconds")
require(
    set(service.get("tmpfs", []))
    == {
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "/var/run/postgresql:size=16m,mode=3775,uid=70,gid=70,noexec,nosuid,nodev",
    },
    "only the bounded runtime directories may be writable outside PGDATA",
)
data_mounts = [
    mount
    for mount in service.get("volumes", [])
    if mount.get("target") == "/var/lib/postgresql/data"
]
require(
    len(data_mounts) == 1 and data_mounts[0].get("type") == "volume",
    "PGDATA must use exactly one Docker volume",
)
require(
    migrator.get("profiles") == ["maintenance"],
    "the migrator must remain outside the default service profile",
)
require(
    migrator.get("image") == services["backend"].get("image"),
    "the migrator must use the exact candidate backend image",
)
require(migrator.get("user") == "appuser", "the migrator must run as appuser")
require(migrator.get("read_only") is True, "the migrator filesystem must be read-only")
require(migrator.get("cap_drop") == ["ALL"], "the migrator must drop all capabilities")
require(
    "no-new-privileges:true" in migrator.get("security_opt", []),
    "the migrator must disable privilege escalation",
)
require(migrator.get("pids_limit") == 64, "the migrator PID limit must remain 64")
require(migrator.get("mem_limit") == "268435456", "the migrator memory limit must remain 256 MiB")
require(not migrator.get("ports"), "the migrator must not publish ports")
require(not migrator.get("volumes"), "the migrator must not mount persistent data")
require(
    migrator.get("entrypoint") == ["python", "manage.py"]
    and migrator.get("command") == ["migrate", "--noinput"],
    "the migrator must run only the reviewed Django migration command",
)
require(
    migrator.get("depends_on", {}).get("db", {}).get("condition") == "service_healthy",
    "the migrator must wait for a healthy database",
)
migrator_environment = migrator.get("environment", {})
require(
    "POSTGRES_USER" not in migrator_environment
    and "POSTGRES_PASSWORD" not in migrator_environment,
    "migration credentials must be inherited ephemerally, not stored in Compose",
)
print(service["image"])
PY
)"

docker compose build db >/dev/null
restore_profile="$(
  docker image inspect "$db_image" \
    --format '{{ index .Config.Labels "com.pcep.restore-profile" }}'
)"
test "$restore_profile" = 'pcep-postgres-16-v1'
docker volume create "$volume" >/dev/null
docker run -d \
  --name "$candidate" \
  --user postgres \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 512m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /var/run/postgresql:rw,noexec,nosuid,nodev,size=16m,mode=3775,uid=70,gid=70 \
  --mount type=volume,src="$volume",dst=/var/lib/postgresql/data \
  -e POSTGRES_DB=hardening_db \
  -e POSTGRES_USER=hardening_admin \
  -e POSTGRES_PASSWORD=hardening-admin-test-only \
  -e PCEP_APP_DB=hardening_db \
  -e PCEP_APP_USER=hardening_user \
  -e PCEP_APP_PASSWORD=hardening-app-test-only \
  -e PCEP_OWNER_ROLE=hardening_owner \
  -e PCEP_MIGRATOR_USER=hardening_migrator \
  "$db_image" >/dev/null

wait_for_database() {
  local remaining=30
  local consecutive=0
  while ((remaining > 0)); do
    if docker exec --user postgres "$candidate" \
      psql -U hardening_user -d hardening_db -Atqc 'SELECT 1' 2>/dev/null \
      | grep -qx '1'; then
      consecutive=$((consecutive + 1))
      if ((consecutive == 3)); then
        return 0
      fi
    else
      consecutive=0
    fi
    remaining=$((remaining - 1))
    sleep 1
  done
  docker logs "$candidate" >&2
  return 1
}

wait_for_database
roles="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_admin -d hardening_db -AtF: -c \
    "SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname IN ('hardening_admin','hardening_migrator','hardening_owner','hardening_user') ORDER BY rolname;"
)"
test "$roles" = $'hardening_admin:t:t:t:t:t:t:t\nhardening_migrator:f:f:f:f:f:f:f\nhardening_owner:f:f:f:f:f:f:f\nhardening_user:t:t:f:f:f:f:f'
owners="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_admin -d hardening_db -AtF: -c \
    "SELECT (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='hardening_db'), (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'), (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='pg_catalog'), (SELECT pg_get_userbyid(extowner) FROM pg_extension WHERE extname='plpgsql'), pg_has_role('hardening_migrator','hardening_owner','MEMBER');"
)"
test "$owners" = 'hardening_owner:hardening_owner:hardening_admin:hardening_admin:t'
if docker exec --user postgres "$candidate" \
  psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 \
  -c 'CREATE TABLE forbidden_table(id integer);' >/dev/null 2>&1; then
  echo "PostgreSQL runtime check failed: the application role created a table" >&2
  exit 1
fi
if docker exec --user postgres "$candidate" \
  psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 \
  -c 'CREATE TEMP TABLE forbidden_temp(id integer);' >/dev/null 2>&1; then
  echo "PostgreSQL runtime check failed: the application role created a temporary table" >&2
  exit 1
fi

docker exec --user postgres "$candidate" \
  psql -U hardening_admin -d hardening_db -v ON_ERROR_STOP=1 \
  -c "ALTER ROLE hardening_migrator LOGIN PASSWORD 'hardening-migrator-test-only' VALID UNTIL 'infinity';" \
  >/dev/null
docker exec --user postgres \
  --env PGPASSWORD=hardening-migrator-test-only \
  --env 'PGOPTIONS=-c role=hardening_owner' \
  "$candidate" \
  psql -h 127.0.0.1 -U hardening_migrator -d hardening_db -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE hardening_probe(id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, payload text NOT NULL);" \
  >/dev/null
docker exec --user postgres "$candidate" \
  psql -U hardening_admin -d hardening_db -v ON_ERROR_STOP=1 \
  -c "ALTER ROLE hardening_migrator NOLOGIN PASSWORD NULL;" \
  >/dev/null

rows="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 -Atqc \
    "INSERT INTO hardening_probe(payload) VALUES ('created-by-app'); UPDATE hardening_probe SET payload='updated-by-app'; SELECT count(*) FROM hardening_probe WHERE payload='updated-by-app';"
)"
test "$rows" = "1"
if docker exec --user postgres "$candidate" \
  psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 \
  -c 'ALTER TABLE hardening_probe ADD COLUMN forbidden integer;' >/dev/null 2>&1; then
  echo "PostgreSQL runtime check failed: the application role altered an owned schema object" >&2
  exit 1
fi
if docker exec --user postgres "$candidate" \
  psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 \
  -c 'CREATE ROLE forbidden_role;' >/dev/null 2>&1; then
  echo "PostgreSQL runtime check failed: the application role created another role" >&2
  exit 1
fi

status="$(docker exec --user postgres "$candidate" cat /proc/1/status)"
grep -Eq '^CapBnd:[[:space:]]+0+$' <<<"$status"
grep -Eq '^NoNewPrivs:[[:space:]]+1$' <<<"$status"
docker exec --user postgres "$candidate" test ! -e /usr/local/bin/gosu
if docker exec --user postgres "$candidate" sh -c 'touch /rootfs-write-probe' 2>/dev/null; then
  echo "PostgreSQL runtime check failed: the root filesystem accepted a write" >&2
  exit 1
fi

docker stop --time 30 "$candidate" >/dev/null
docker start "$candidate" >/dev/null
wait_for_database
roles="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_admin -d hardening_db -AtF: -c \
    "SELECT rolcanlogin,rolpassword IS NULL FROM pg_authid WHERE rolname='hardening_migrator';"
)"
test "$roles" = 'f:t'
rows="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_user -d hardening_db -Atqc \
    'SELECT count(*) FROM hardening_probe;'
)"
test "$rows" = "1"

echo "Hardened PostgreSQL container check passed."
