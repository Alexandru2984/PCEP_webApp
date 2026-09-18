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

The Python runner limits source to 20,000 characters, output/tracebacks to
10,000 characters, queued/running jobs to four, startup to 30 seconds and each
execution to eight seconds. Timeout terminates the worker; later Run recreates
it. Failed startup/crash also permits retry. These are responsiveness/resource
protections, not a hardened sandbox: arbitrary Python can use the JavaScript
bridge and can still exhaust browser memory before a timeout. Do not run
untrusted snippets in an authenticated admin browser.

## Nginx production topology and hardening

The tracked vhost now matches the existing TLS deployment, including SEO,
ACME, sitemap and robots routes. It requires the installed Let's Encrypt
certificate, shared `block-dotfiles.conf`, and host Cloudflare real-IP and
`$from_cloudflare_origin` definitions. The shared tunnel connects to HTTPS
loopback; Nginx restores CF-Connecting-IP only for trusted peers and overwrites
X-Forwarded-For with that verified address. Django still trusts one proxy hop.
No shared tunnel/firewall configuration was changed.

Install `nginx/snippets/pcep-*.conf` into `/etc/nginx/snippets/` before installing
the vhost. Back up outside sites-enabled, run `sudo nginx -t`, then use
`sudo systemctl reload nginx` (graceful). The 2026-09-18 vhost backup is in
`/home/micu/backups/pcep/security-20260918/nginx.before`.
The API has a shared 3 requests/second IP limit with a burst of 30, 64 KB body
limit, short connection timeout and JSON 413/429 errors. Admin retains its
20/minute limit and Django CSRF behavior. The analytics proxy exposes only
GET tracker script and POST event collection; its dashboard is not routed.
Hashed assets get immutable caching and real 404s for missing files; shell,
worker, Pyodide and study pages send no-cache/no-store/must-revalidate.
Cloudflare initially imposed its four-hour default TTL on plain no-cache
JavaScript responses. Public GET/HEAD requests now report BYPASS with the stronger
policy; verify both origin and public cache headers after each deployment. Common headers cover worker, SEO,
API and errors. CSP retains WASM compilation and the already enabled
Cloudflare beacon origins, removes the obsolete external Umami origin and
never grants unsafe-eval. COEP is deliberately not added: runner operation does
not require shared memory or cross-origin isolation.
Structured PCEP Nginx logs at `/var/log/nginx/pcep_access.log` carry generated
request IDs, path, status and timing, without client IPs, query strings,
cookies or authorization headers. Existing Nginx log rotation covers them.

## Study interface and recovery

The exam navigator collapses initially on small screens, uses five mobile
columns with 44 px targets, and offers next-unanswered/next-flagged jumps.
The timer stays visible while scrolling, announces the one-minute warning
without reading every tick, and uses a real deadline. Submit confirmation wraps
and manages focus; quitting asks before losing unsubmitted answers.
Question/result headings receive focus on navigation; answer options and
workspace navigation use native buttons. A skip link, visible focus, scrollable
keyboard-accessible code and reduced-motion styles apply throughout.
Keyboard help is available in the footer. Shortcuts ignore typing, modifiers,
composition and repeated keys. Offline and persistence warnings explain recovery.
A failed screen/chunk load offers reload and states the unsubmitted-session risk.
Axe and overflow checks run through the study screens in both themes at
360/390/430/768/1024/1280/1440 px; they supplement manual inspection, not a claim
of complete accessibility certification.

## PWA update and cache policy

`frontend/pwa.config.js` contains the tested cache policy. Only the public shell
is precached. Runtime caching accepts HTTP 200 same-origin `/pyodide/` files in
`pyodide-runtime-0.29.4`; opaque responses and API feedback are excluded.
API/admin/static/media, study pages, analytics, asset/runtime paths and
robots/sitemap are exempt from offline SPA navigation fallback. A controller
update shows a notice; reload is the user's action after finishing the session.
Active tabs are not automatically reloaded. The download script validates every
pinned core file and stages downloads before replacing build inputs, preserving
an older runtime on failure. No answer database is downloaded for offline use.
Existing Umami tracking respects Do Not Track and excludes URL query/hash data
([tracker configuration](https://docs.umami.is/docs/tracker-configuration));
no new analytics service or user identifier was added.
