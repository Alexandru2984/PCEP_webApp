# Operations Runbook

This project is deployed as a Dockerized Django API behind system nginx, with a
static Vite build served from `/var/www/pcep/frontend`.

## Daily Checks

```bash
make status
curl -fsS https://pcep.micutu.com/api/health/
DJANGO_SETTINGS_MODULE=pcep_project.test_settings backend/.venv/bin/python backend/manage.py audit_questions --fail-on-warnings
```

## Local Verification

```bash
make install
make test
make audit
make django-check
```

`make test` runs the local SQLite-backed backend test suite plus the frontend
lint/format/build checks. CI runs the backend suite against PostgreSQL.

## Backend Deploy

```bash
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/micu/backups/pcep
docker exec pcep_db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "/home/micu/backups/pcep/pcep_db_${stamp}.sql.gz"

docker compose build backend
docker compose up -d backend
curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:8001/api/health/
docker compose exec backend python manage.py audit_questions --fail-on-warnings
docker compose exec backend python manage.py seed_questions --dry-run
docker compose exec backend python manage.py seed_questions --reset
```

The direct loopback health probe includes `X-Forwarded-Proto: https` because
production Django redirects plain HTTP when called without the nginx proxy
headers.

## Frontend Deploy

```bash
make deploy-frontend
curl -fsS https://pcep.micutu.com/ >/dev/null
```

The deploy target backs up the existing static directory as
`/var/www/pcep/frontend.bak.<timestamp>` before publishing `frontend/dist`.

### In-browser Python runner (Pyodide)

`make build-frontend` depends on `fetch-pyodide`, which downloads the self-hosted
Pyodide runtime into `frontend/public/pyodide/` (git-ignored, ~12 MB) only when
it is missing. `vite build` then copies it into `dist/`, so it publishes
same-origin at `/pyodide/*` alongside `/py-worker.js` — no third-party CDN.

The SPA `location /` block in `nginx/pcep.micutu.com.conf` already grants the two
CSP capabilities the runner needs: `worker-src 'self'` (the Web Worker) and
`script-src 'wasm-unsafe-eval'` (WASM compilation). No `'unsafe-eval'` is required.
After changing the live vhost, keep backups **outside** `sites-enabled/`
(e.g. `/etc/nginx/_mybackups/`) so a stray `.bak` is not parsed as a second vhost,
then `sudo nginx -t && sudo systemctl reload nginx`.

Smoke-test after deploy:

```bash
curl -fsS https://pcep.micutu.com/py-worker.js -o /dev/null
curl -fsS https://pcep.micutu.com/pyodide/pyodide.asm.wasm -o /dev/null   # ~8 MB, application/wasm
```

## Rollback

Frontend rollback:

```bash
rm -rf /var/www/pcep/frontend
cp -a /var/www/pcep/frontend.bak.<timestamp> /var/www/pcep/frontend
```

Database rollback:

```bash
gunzip -c /home/micu/backups/pcep/pcep_db_<timestamp>.sql.gz \
  | docker exec -i pcep_db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

For a full rollback, restore the DB backup first, then redeploy the matching
frontend build and backend image.
