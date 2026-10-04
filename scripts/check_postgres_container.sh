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
docker compose config --format json >"$config_file"

db_image="$(python3 - "$config_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    service = json.load(config_file)["services"]["db"]


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
print(service["image"])
PY
)"

docker compose build db >/dev/null
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
  "$db_image" >/dev/null

wait_for_database() {
  local remaining=30
  while ((remaining > 0)); do
    if docker exec --user postgres "$candidate" \
      psql -U hardening_user -d hardening_db -Atqc 'SELECT 1' 2>/dev/null \
      | grep -qx '1'; then
      return 0
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
    "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname IN ('hardening_admin','hardening_user') ORDER BY rolname;"
)"
test "$roles" = $'hardening_admin:t:t:t:t:t\nhardening_user:f:f:f:f:f'
owners="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_admin -d hardening_db -AtF: -c \
    "SELECT (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='hardening_db'), (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='pg_catalog'), (SELECT pg_get_userbyid(extowner) FROM pg_extension WHERE extname='plpgsql');"
)"
test "$owners" = 'hardening_user:hardening_admin:hardening_admin'
rows="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_user -d hardening_db -v ON_ERROR_STOP=1 -Atqc \
    'CREATE TABLE hardening_probe(id integer PRIMARY KEY); INSERT INTO hardening_probe VALUES (1); SELECT count(*) FROM hardening_probe;'
)"
test "$rows" = "1"
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

docker restart --time 30 "$candidate" >/dev/null
wait_for_database
rows="$(
  docker exec --user postgres "$candidate" \
    psql -U hardening_user -d hardening_db -Atqc \
    'SELECT count(*) FROM hardening_probe;'
)"
test "$rows" = "1"

echo "Hardened PostgreSQL container check passed."
