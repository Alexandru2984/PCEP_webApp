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
unit/lint/format/build checks. CI runs the backend suite against PostgreSQL.

## Backend Deploy

```bash
set -euo pipefail
umask 077
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/micu/backups/pcep
chmod 700 /home/micu/backups/pcep
docker tag "$(docker inspect pcep_backend --format '{{.Image}}')" "pcep-backend-rollback:${stamp}"
docker exec pcep_db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "/home/micu/backups/pcep/pcep_db_${stamp}.sql.gz"
gzip -t "/home/micu/backups/pcep/pcep_db_${stamp}.sql.gz"

docker compose build backend
# Check the candidate/migration plan before this controlled single-service replacement.
docker compose up -d --no-deps backend
curl -fsS https://pcep.micutu.com/api/health/
docker compose exec backend python manage.py check --deploy --fail-level WARNING
docker compose exec backend python manage.py audit_questions --database --fail-on-warnings
```

Never reset/reseed the live bank during routine deployment: question IDs are
referenced by local progress. Startup runs pending migrations and collectstatic.
The API has three workers, 30-second request/graceful timeouts, a 45-second
container shutdown grace period, and a bounded 60-second database startup probe
(`DB_STARTUP_TIMEOUT_SECONDS`, 1..300). Failed migrations stop startup.
The non-root backend filesystem is read-only except the existing static/media
volumes and a 64 MB temporary filesystem. Capabilities are dropped, privilege
escalation is disabled, and the backend is capped at 512 MB and 128 processes.
PostgreSQL volumes, privilege requirements and binding are unchanged.
Healthchecks use the first configured allowed hostname and forwarded HTTPS;
local hostnames are not required in production ALLOWED_HOSTS. `/api/health/`
remains readiness. Gunicorn logs request ID, method, path, status and duration,
without bodies, cookies, authorization or query strings.

## Frontend Deploy

```bash
make deploy-frontend
curl -fsS https://pcep.micutu.com/ >/dev/null
```

The target checks the pinned runtime, completes the build and validates required
files and referenced HTML assets. It copies to a staging directory on the live
filesystem, backs up the current root under BACKUP_ROOT, retains older hashed
assets for open tabs, then uses Linux renameat2 directory exchange. Copy,
validation and exchange failures leave the live root intact. The previous root
is retained beside it as `.frontend.previous-<timestamp>-<id>`.
`FRONTEND_ROOT`, `BACKUP_ROOT` and `PYTHON` can be overridden. Python accepts
relative paths, absolute paths or executables from PATH. Linux atomic exchange
support is required; the script refuses to fall back to delete-then-copy.
Monitor backup/retained-chunk disk usage; no automatic deletion is performed.
The prior stale backend virtualenv was archived under security-20260918; local
checks now use a separate Python 3.12.14 environment without changing host Python.
Node 24 LTS is used in CI and the non-root frontend builder because Node 20 is EOL
([Node release status](https://nodejs.org/en/about/previous-releases)).

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
backend/.venv/bin/python scripts/publish_release.py \
  /var/www/pcep/.frontend.previous-<timestamp>-<id> /var/www/pcep/frontend \
  --backup-root /home/micu/backups/pcep
```

Backend rollback uses the retained image: tag the chosen
`pcep-backend-rollback:<timestamp>` as `pcep_webapp-backend:latest`, then
`docker compose up -d --no-deps --no-build backend` and verify readiness/public
API. The 2026-09-18 pre-change image is `pcep-backend-rollback:20260918`.
It contains old vulnerable dependencies, so use only for an emergency rollback.
Migration 0003 only labels an existing option; it needs no database restore for
an application rollback. Database restoration is a separate planned maintenance
operation into a suitable database, never an automatic pipe into the running
production database.

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
`GET /api/search/` accepts a required 2–80 character `q`, optional valid module
and difficulty filters, and a `limit` from 1 to 20. It performs one bounded query
and returns only question ID, text, code, module and difficulty. Choices,
explanations and answer metadata are deliberately absent. A selected drill sends
only unique IDs to `quiz-set`, which returns fresh public choices under the
existing answer-leakage contract.
`GET /api/daily/` returns five public questions for the current
`Europe/Bucharest` date. Selection is deterministic for the date and production
secret, covers every populated syllabus module before filling the fifth slot, and
reads only IDs/modules during ranking. The returned questions use the same public
serializer as `quiz-set`; correctness and explanations remain server-side until
submission. Rotating `DJANGO_SECRET_KEY` can change that day's set. The browser
stores only the challenge date on the bounded attempt record, so completion and
score remain local and portable; replaying the challenge is allowed.
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
for history, mistakes, bookmarks and personal notes is bounded to 100 records;
each note is limited to 2,000 characters. The per-question review schedule is
bounded to 1,000 compact records. The progress screen exports backup format v3,
previews and merges strictly validated imports up to 8 MB, and still accepts
existing v1 and v2 backups. History, mistakes, bookmarks, notes and the review
schedule can be reset independently. Backups contain public question options,
aggregate performance, optional confidence ratings, daily challenge dates,
bounded response-time totals, review dates and user-written notes, never answer
keys or explanations. Keep backups private if you want to keep your study history
and notes private; nothing is uploaded by these features.
Bookmarks are available on question cards. Bookmark and mistake drills fetch
current public question data using the bounded `ids` quiz-set filter, avoiding
stale choice IDs after admin edits. Module/difficulty accuracy includes mixed
sessions completed in this version. Flashcard self-ratings are excluded from
graded accuracy. Older mixed attempts lack detailed breakdowns and remain visible
in history without invented module performance.

Personal notes are available during practice and in the completed-session review,
but hidden during exam simulation. They are rendered as plain React text, merged
by their last-updated timestamp during import and stored by question ID without
choices, correctness flags or explanations.

Completed practice, exam and flashcard sessions update an explainable local review
schedule. Consecutive successful reviews use 1, 3, 7 days and then double up to a
60-day cap. A missed or skipped question becomes due immediately. Due drills send
at most 20 question IDs to the existing quiz-set endpoint and receive fresh public
question data; the schedule stores no choices, selected choice IDs, explanations
or correctness key. An optional per-question confidence value (`low`, `medium` or
`high`) is stored with the latest review. Dashboard mastery combines observed
accuracy, repetition and the achieved interval, and should be treated as a study
signal rather than an exam credential.

Adaptive practice is also local and rule based. It ranks at most 20 unique
question IDs using a documented score: +100 when due, +60 while in the mistakes
list, up to +40 from observed error rate, up to +30 from the mastery gap, +20 when
the latest confidence is low, and a small +5/+10 medium/hard bonus. Questions at
or above 80% mastery are omitted unless currently due, missed or their latest
recorded confidence is low. Equal scores prefer the least recently attempted
question, then its numeric ID, so the plan is deterministic and testable. Only
the selected IDs are sent to `quiz-set`; fresh public questions come back without
answer metadata.

Dashboard momentum is derived only from the bounded local attempt history. Study
streaks count unique local calendar days and remain current through the day after
the latest session. Score trends compare up to five recent graded sessions with
an equally sized preceding window using question-weighted accuracy. Average pace
prefers measured time to the first answer for sessions created by this version;
legacy sessions fall back to total elapsed time divided by graded questions.
Confidence calibration compares aggregate high-confidence misses and
low-confidence successes. Flashcards count as study activity but are excluded from
performance, confidence calibration and pace because their result is self-rated.

## Active exam recovery

An in-progress exam is stored separately under the versioned
`pcep.activeExam` key. It contains only sanitized public questions, the learner's
selected choice IDs, optional confidence ratings, bounded time-to-first-answer
values, flags, current index, start time and original deadline. It never contains
correctness flags, explanations or a correct-choice ID, and it is not included in
progress exports. Only one active exam is retained. A failed grading request keeps
the exact answer, confidence and timing snapshot for a safe retry.

On reload the setup screen requires an explicit choice: resume the saved exam or
discard it before starting any quiz or dashboard drill. Resuming preserves the
original wall-clock deadline. If that deadline passed while the app was closed,
the saved answers are locked and submitted for grading immediately; a network
failure keeps the recovery copy for retry. Successful grading, Quit and Discard
remove it. Strict schema validation rejects unknown questions/choices, duplicate
flags, invalid timestamps and extra top-level fields. Abandoned data expires 24
hours after its deadline. Storage failure uses the existing persistence warning
and never blocks the live in-memory exam.

The Python runner limits source to 20,000 characters, output/tracebacks to
10,000 characters, queued/running jobs to four, startup to 30 seconds and each
execution to eight seconds. Timeout terminates the worker; later Run recreates
it. Failed startup/crash also permits retry. These are responsiveness/resource
protections, not a hardened sandbox: arbitrary Python can use the JavaScript
bridge and can still exhaust browser memory before a timeout. Do not run
untrusted snippets in an authenticated admin browser.

The question audit canonicalizes valid Python snippets through the standard AST
before duplicate comparison. This catches semantically identical questions that
differ only in quote style or harmless formatting. Intentionally invalid teaching
snippets fall back to normalized source comparison and are not rejected merely for
being invalid Python.

Migration `0004_replace_duplicate_exception_question` replaces one duplicate
exception question with a distinct `try/except/else` exercise. It updates the
existing question and its four choices in place, preserving every database ID and
avoiding stale local bookmarks or interrupted exam selections.

Use `audit_questions --show-similar` to list conservative near-duplicate
candidates within the same module. These are informational because deliberate
contrast pairs can be very similar; `--fail-on-warnings` continues to fail only
on definite duplicates, coverage warnings and integrity errors. Migration
`0005_replace_equivalent_comprehension` replaces one logically equivalent list
comprehension while preserving its question and choice IDs.

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
The exact `/manifest.webmanifest` location supplies
`application/manifest+json`; the stock Nginx MIME table otherwise serves that
extension as `application/octet-stream` and browsers may ignore installation
metadata.
Cloudflare initially imposed its four-hour default TTL on plain no-cache
JavaScript responses. Public GET/HEAD requests now report BYPASS with the stronger
policy; verify both origin and public cache headers after each deployment. Common headers cover worker, SEO,
API and errors. CSP retains WASM compilation and the already enabled
Cloudflare beacon origins, removes the obsolete external Umami origin and
never grants unsafe-eval. COEP is deliberately not added: runner operation does
not require shared memory or cross-origin isolation.
Cloudflare currently injects a dynamic inline JavaScript-detection challenge at
the edge. The strict CSP blocks it and Chromium reports the expected violation;
the origin response does not contain that script. Disable the corresponding
Cloudflare bot/JavaScript-detection feature if it is unnecessary. Do not add
`unsafe-inline` or per-response dynamic hashes to accommodate it.
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


## Static assets and CI

After upgrading Django, publish fresh collectstatic output to the host static
root: Nginx serves a host copy, not the Docker volume directly. Copy the
container's `/app/staticfiles/.` to a staging source, then run
`python scripts/publish_release.py <source> /var/www/pcep/static --kind static --backup-root /home/micu/backups/pcep`.
The publisher makes staged directories traversable and files readable by Nginx,
even when a source created with `mktemp` starts at mode 0700. The same atomic
swap keeps the old fingerprinted admin assets available for rollback.
Do not run the destructive `seed-reset` target as deployment; it now requires
explicit `ALLOW_QUESTION_RESET=yes`.
CI cancels obsolete runs, caches npm/Python/Pyodide downloads, bounds Playwright
to two workers, uploads HTML reports/traces, validates the vhost with disposable
certificates in an isolated Nginx container, and builds the hardened backend.
Browser tests use mocked APIs; Python execution uses the real self-hosted runtime.
They never call production from CI.
