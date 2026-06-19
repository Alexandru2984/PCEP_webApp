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
