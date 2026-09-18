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

## Public study pages

`/usr/local/sbin/pcep-seo-pages` is deployed from `scripts/pcep-seo-pages.py`.
`pcep-seo-pages.timer` regenerates the host pages weekly. It extracts questions
through the public API serializer: static pages must never contain correct-answer
flags, answer IDs or per-option explanations. Answers are obtained only after
interactive submission. Validate with `pytest quiz/tests/test_seo_pages.py`.
Deploy with `sudo install -m 755 scripts/pcep-seo-pages.py /usr/local/sbin/pcep-seo-pages`
and `sudo /usr/local/sbin/pcep-seo-pages`. No service restart is necessary.
The 2026-09-18 security remediation backed up the previous generator and pages
under `/home/micu/backups/pcep/security-20260918`. Do not restore the vulnerable
pages. Search engines or third-party caches may retain historical answer content.

## API contracts and probes

`GET /api/live/` checks process liveness without accessing PostgreSQL.
`GET /api/health/` remains database readiness (200/up or 503/down); existing
container/monitor checks keep using it. All API responses carry `no-store`.
Grading accepts at most 100 unique question IDs and preserves submitted order.
IDs must be positive JSON integers within signed 64-bit range. Omitted/null
choices count as wrong; foreign choices and duplicate questions return 400 with
no answer feedback. Retrying the same valid submission is safe and stateless.
An invalid answer key returns 503 instead of an ambiguous score.
Django ignores X-Forwarded-Host; the origin proxy must overwrite Host and
X-Forwarded-For and supply X-Forwarded-Proto. NUM_PROXIES remains exactly 1.

## Question integrity

Audit the seed with `python manage.py audit_questions --fail-on-warnings` and
live data with `docker compose exec backend python manage.py audit_questions --database --fail-on-warnings`.
The database audit is read-only and reports affected database IDs. Questions
require four unique non-empty options, one boolean correct flag, an explanation
per option, valid module/difficulty and a non-empty prompt. The question admin
validates the complete inline set; the separate choice admin is view-only.
Seed validation runs before any writes, including an explicitly requested reset.
Migration `0003_label_empty_output_choice` changes only the empty wrong option
for `print(0 or "" or "x" or "y")` to `(empty output)`, preserving all IDs and
explanations. It is reversible and does not recreate the question bank.

## Local progress and portability

Progress now uses the versioned `pcep.progress` record. Valid legacy
`pcep.history`/`pcep.mistakes` records are read and migrate only after a complete
successful write. A failed import leaves the previous record intact. Each list
is bounded to 100 records. The progress screen exports JSON, previews and merges
strictly validated imports up to 8 MB, and resets history, mistakes or bookmarks
individually. Backups contain public question options and aggregate performance,
never answer keys or explanations. Keep backups private if you want to keep your
study history private; nothing is uploaded by these features.
Bookmarks are available on question cards. Bookmark and mistake drills fetch
current public question data using the bounded `ids` quiz-set filter, avoiding
stale choice IDs after admin edits. Module/difficulty accuracy includes mixed
sessions completed in this version. Flashcard self-ratings are excluded from
graded accuracy. Older mixed attempts lack detailed breakdowns and remain visible
in history without invented module performance.
