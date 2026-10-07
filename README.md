# PCEP Quiz

[![CI](https://github.com/Alexandru2984/PCEP_webApp/actions/workflows/ci.yml/badge.svg)](https://github.com/Alexandru2984/PCEP_webApp/actions/workflows/ci.yml)
[![Production smoke](https://github.com/Alexandru2984/PCEP_webApp/actions/workflows/production-smoke.yml/badge.svg)](https://github.com/Alexandru2984/PCEP_webApp/actions/workflows/production-smoke.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2_LTS-092E20.svg)](https://www.djangoproject.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)

A practice-quiz web app for the **PCEP™ — Certified Entry-Level Python Programmer**
certification. Every question gives instant feedback and a per-option explanation that
tells you _why_ each wrong answer is wrong — so you learn the concept, not just the key.

🔗 **Live:** [pcep.micutu.com](https://pcep.micutu.com)

> Questions are organised by the four official PCEP-30-02 syllabus modules, all 15
> objectives and difficulty, so you can drill a precise weak area or take a full mixed
> mock exam.

## Screenshots

| Practice mode (dark)                                        | Exam simulation (light)                     |
| ----------------------------------------------------------- | ------------------------------------------- |
| ![Practice](docs/screenshots/03-practice-feedback-dark.png) | ![Exam](docs/screenshots/04-exam-light.png) |

| Review & explanations                           | Progress dashboard                                    |
| ----------------------------------------------- | ----------------------------------------------------- |
| ![Review](docs/screenshots/05-review-light.png) | ![Dashboard](docs/screenshots/06-dashboard-light.png) |

| Run any snippet right in the question (Pyodide / WebAssembly) |
| ------------------------------------------------------------- |
| ![Code runner](docs/screenshots/07-code-runner-light.png)     |

| End-of-quiz report with one-click drills        | Flashcards study mode                                   |
| ----------------------------------------------- | ------------------------------------------------------- |
| ![Report](docs/screenshots/08-report-light.png) | ![Flashcards](docs/screenshots/09-flashcards-light.png) |

## Features

- 📚 **300+ questions** across all four PCEP modules with syntax-highlighted code
- 🐍 **Run the code, don't just read it** — every snippet has a built-in Python
  interpreter (Pyodide on WebAssembly). Edit it, hit **Run**, and see real
  `stdout`/tracebacks **entirely in your browser** — no backend, no server cost.
  Each run lives in a replaceable worker on a dedicated, capability-free origin,
  reached through a bounded private message channel. CSP prevents that origin
  from contacting the learner app. Startup, execution, source, queue and output
  limits protect responsiveness; browser memory exhaustion is still possible.
- 🎯 **Per-option explanations** — a wrong pick explains the exact misconception
  _and_ why the correct answer is right (skipped exam questions included)
- ⏱️ **Three study modes** — Practice (instant feedback), a timed **Exam
  simulation** (question navigator, flagging, auto-submit), and **Flashcards**
  (flip to reveal the answer, self-mark what you know). Reveal failures are retryable,
  and leaving the deck cancels pending work. Exam mode includes a
  [PCEP-30-02](https://pythoninstitute.org/pcep) full-mock preset with 30 questions,
  40 minutes and the official 7/8/7/8 module item distribution; the UI clearly notes
  that this trainer does not reproduce the official interactive item formats.
- 💾 **Crash-safe session recovery** — an interrupted exam restores its live deadline,
  selections and flags, Practice resumes at the current question or already submitted
  feedback, and Flashcards restores the current card plus any answer already revealed.
  Every mode uses a validated local-only copy, requires confirmation before discard and
  keeps answer keys out of every unanswered or unrevealed question. A completed session
  reaches its report only after the progress snapshot is stored and its recovery copy is
  removed; a failed step remains retryable without counting the same session twice.
- 🧠 **Local review schedule** — an explainable 1, 3, 7, 14… day study cycle,
  due-review drills in Practice or Flashcards, per-question mastery and transparent
  adaptive study in Practice or Flashcards that also prioritizes low-confidence
  answers, without accounts or tracking. Saved mistakes and bookmarks can also be
  studied as graded Practice or self-rated Flashcard decks.
- 📅 **Daily challenge** — five deterministic questions with all four syllabus modules,
  a local completion score and the same answer-safe set throughout the Bucharest day
- 🧩 **Filter by module, syllabus objective & difficulty**, then choose a quick 5-question
  drill or a 10, 20, 30 or 50-question session
- 🔎 **Search question text or Python code** and build a focused Practice or Flashcard
  drill from up to 20 matches; search previews deliberately exclude choices and answer
  metadata
- 📊 **Progress dashboard** — bounded attempt history, weighted module/objective/
  difficulty accuracy, confidence calibration, local-day study streaks, score trends,
  measured response pace, separate full-mock history and separate flashcard self-ratings
  in both reports and history (local-first)
- 📈 **End-of-quiz report** — per-module, per-objective, per-difficulty and optional
  confidence breakdowns, decision timing and a precise "focus area" recommendation you
  can drill in one click, plus a focused review queue combining misses with correct
  answers given at low confidence; launch that exact queue immediately as graded
  Practice or self-rated Flashcards
- 🔁 **Practice your mistakes** — missed questions are saved locally and re-served
  as a focused Practice or Flashcard drill; a correct/self-rated success removes the
  question from the list (local-first)
- 🔖 **Bookmarks and portable progress** — Practice and Flashcard bookmark drills plus validated,
  versioned JSON export/import and selective history, review, mistake, note and bookmark resets
- 📝 **Private personal notes** — keep bounded local notes beside practice questions and
  review them after a session; notes are included in validated progress backups
- ⌨️ **Keyboard shortcuts** and full dark mode
- 📱 **Installable, offline-capable PWA** — eligible browsers offer a clear in-app
  install action; a service worker precaches the public shell and caches the Pyodide
  runtime. API answers and study pages are excluded, and the UI explains that new
  questions and feedback still need a connection. Offline mode never downloads the
  answer bank. App-shell updates wait for a learner-approved reload so an active exam
  is not replaced mid-session.
- ✅ Scored against the official **70% pass threshold**
- 🔒 **Answer keys never leave the server** until you submit (no cheating via DevTools)
- 🛡️ Rate-limited API, hardened production settings, separate process liveness
  and database readiness probes, plus scheduled read-only production contract
  monitoring without learner telemetry
- 🛡️ Non-root, read-only application and PostgreSQL containers with dropped
  capabilities, bounded resources, digest-pinned bases and blocking image scans
- 🔎 AST-backed question audits catch duplicates, malformed answer sets, short or
  editorial explanations, missing/cross-module objectives and out-of-syllabus syntax
  before release; PostgreSQL also rejects a second correct choice for one question

## Tech stack

| Layer    | Tech                                                              |
| -------- | ----------------------------------------------------------------- |
| Backend  | Django 5.2 LTS · Django REST Framework · PostgreSQL · Gunicorn    |
| Frontend | React 18 · Vite · Tailwind CSS 4 · Axios · Pyodide (WASM)         |
| Tooling  | pytest · Vitest · ESLint · Prettier · GitHub Actions CI/smoke     |
| Deploy   | Docker Compose · system Nginx · Cloudflare Tunnel · Let's Encrypt |

## Architecture

```
Internet → Cloudflare → cloudflared → HTTPS loopback Nginx
                                      ├── /admin*         → 404 (publicly disabled)
                                      ├── /api/           → 127.0.0.1:8001
                                      │                     → Docker: Gunicorn → PostgreSQL
                                      ├── /practice/      → generated public study pages
                                      └── /               → /var/www/pcep/frontend

pcep-runner.micutu.com → static bridge + Pyodide only (no API/auth/SPA fallback)
```

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes --only-binary=:all: -r requirements-dev.txt

# Use a migration-capable local credential for schema changes, then switch to
# the restricted application credential before running the server.
export DJANGO_SECRET_KEY=dev DJANGO_DEBUG=True
export POSTGRES_HOST=localhost POSTGRES_DB=pcep_db POSTGRES_USER=local_migrator POSTGRES_PASSWORD=...
python manage.py migrate
export POSTGRES_USER=pcep_user POSTGRES_PASSWORD=...
python manage.py seed_questions          # idempotent: adds missing questions
python manage.py runserver
```

### Frontend

Use Node 24.21.0 with npm 11.19.0. The installer blocks every dependency lifecycle
script and verifies the exact lockfile and installed-package inventory. The current
graph needs no lifecycle installer; the manifest also blocks optional `fsevents` as
defense in depth for npm releases that support `allowScripts`.

```bash
cd frontend
bash scripts/install-dependencies.sh
npm run fetch-pyodide   # one-time: downloads the self-hosted Python runtime (~12 MB,
                        # git-ignored) used by the in-browser code runner
npm run dev             # Vite dev server, proxies /api to Django (see vite.config.js)
```

> The build succeeds without the Pyodide step, but the **Run** button needs it.
> `npm run build` copies `public/pyodide/` into `dist/`, but production serves the
> runtime only from `https://pcep-runner.micutu.com`. The learner origin explicitly
> returns 404 for runner files and does not grant `'wasm-unsafe-eval'`.

### With Docker

```bash
cp .env.example .env          # Django and its least-privilege database role
cp .env.db.example .env.db    # separate PostgreSQL administrator/bootstrap role
docker volume create pcep_webapp_postgres_data
docker volume create pcep_webapp_static_volume
docker volume create pcep_webapp_media_volume
docker compose up --build     # db + backend on 127.0.0.1:8001
make compose-build-frontend       # build React through the pinned Node image
```

The three named volumes are external by design: Compose uses them but cannot
remove them during teardown. If you customize their names in `.env`, create the
matching volumes before the first start.

## Testing & quality

The browser suite checks setup, practice, exam, review, progress, flashcards,
offline recovery and the real Pyodide runtime. Axe and horizontal-overflow checks
cover both themes at 1440, 1280, 1024, 768, 430, 390 and 360 px. These automated
checks supplement manual review; they are not a blanket accessibility certification.

```bash
make test
make audit
make django-check
make compose-build && make audit-image
bash scripts/check_postgres_container.sh && make audit-db-image
make production-smoke

# After intentionally changing a Python requirement:
make lock-backend

# Backend — 296 tests (API/security, backup, integrity, startup, release, SEO and smoke behavior)
# Local tests use in-memory SQLite; CI also runs the API suite against PostgreSQL.
cd backend && python -m pytest
DJANGO_SETTINGS_MODULE=pcep_project.test_settings python manage.py audit_questions --fail-on-warnings
# Add --show-similar for conservative near-duplicate candidates requiring human review.

# Frontend — 313 Vitest tests, then static checks, the production build and
# 31 Playwright flows (including axe, daily challenge, full mock, confidence, PWA,
# notes, search, adaptive study, session recovery and Pyodide).
cd frontend && npm run test && npm run lint && npm run format:check && npm run build
cd frontend && npm run e2e
```

Push/PR CI runs the backend, frontend, audit and build checks without calling
production, plus `manage.py check --deploy` against a production-like config.
An independent CodeQL workflow analyzes GitHub Actions, Python and
JavaScript/TypeScript on every push and pull request to `main`, weekly, and on
manual dispatch. It runs GitHub's `security-extended` query suite and uploads
results with a job-scoped `security-events: write` permission; all action
revisions are pinned to reviewed commit SHAs.
Its jobs use the explicit Ubuntu 24.04 runner image; Python jobs use the same
3.12.14 patch release as the backend runtime, avoiding unreviewed toolchain changes
when GitHub advances its `ubuntu-latest` alias.
The ops job validates every workflow with checksum-pinned `actionlint` and
`zizmor` releases: embedded shell blocks are checked, action references must be
immutable and dangerous permissions, triggers and expression use are rejected.
The ops job also scans every tracked file and the complete reachable Git history
for known secret formats using the same digest-pinned Trivy image as container
auditing. Ignored `.env` files and other untracked operator state are never copied
into the scanner.
Its Nginx job starts a disposable TLS vhost and verifies the actual 413/429 JSON,
cache, CSP, request-ID and retry contracts in addition to configuration syntax.
It also resolves and validates every repository-owned systemd service, timer and
drop-in so unsupported directives or orphan overrides cannot reach an operator.
Its pinned Trivy scan fails on HIGH/CRITICAL operating-system or Python findings
that have a vendor fix, while still reporting separately tracked findings without
a patch.
The separate **Scheduled dependency audit** runs daily at 04:17 UTC and on manual
dispatch, so newly published Python or Node advisories are detected even when no
push or pull request occurs. It has read-only repository permissions and installs
the Node tree with package scripts disabled before auditing the committed lockfile.
Both push/PR CI and the scheduled job also verify npm registry signatures and
provenance attestations for the resolved dependency tree.
The frontend pins Workbox's deprecated `glob@11` transitive dependency to
`glob@13.0.6`; Workbox uses only the retained `globSync` library API. Keep this
override exact and remove it when Workbox supports the current major directly.
Dependabot checks GitHub Actions every Monday, frontend npm dependencies every
Tuesday and backend Python dependencies every Wednesday. Python's conventional
`.in` manifests and SHA-256 `.txt` locks are regenerated and checked together.
Normal version updates wait seven days after release and group compatible
minor/patch changes; the cooldown does not apply to security-update PRs. Dependabot
security updates are enabled, but every proposal still triggers the full CI suite
and awaits human review—nothing is auto-merged by this configuration.
The repository dependency graph and Dependabot alerts are enabled, and the project
includes a required PR-only GitHub dependency review workflow. It fails on newly
added or upgraded dependencies with
moderate-or-higher known vulnerabilities in runtime, development or unknown scopes.
The review has read-only repository access, neither comments on the PR nor grants
write permission, and deliberately does not enforce a license allowlist until the
project adopts a reviewed license policy. Protected `main` also requires all four
CI jobs, an up-to-date PR branch, resolved conversations and linear history.
The separate **Production smoke** workflow runs every six hours and on manual
dispatch. It uses bounded read-only requests to verify the public shell and its
entry assets, separate frontend/backend release identities, liveness/readiness,
security/cache headers,
all aggregate matrices, answer secrecy across quiz, daily, detail and search
responses, and ordered targeted drills.

Production builds identify themselves without analytics or an extra API call:
the frontend revision is shown in the footer and a static shell metadata marker,
while Django API responses include the backend revision in `X-PCEP-Release`. The
Make deploy/build targets inject the current Git revision automatically.

`make deploy-backend` snapshots the running image and creates a verified private
database dump before it can replace the local image tag, then checks and deploys
only the backend service. Schema changes run in a separate, one-shot hardened
container through a normally disabled migration login; the long-lived Django role
has DML access but cannot own or create database objects. A separate hardened
systemd timer creates a private,
checksummed logical backup every day and retains 30 successful daily copies; use
`make backup-database` for the same operation manually. A weekly timer restores the
newest verified daily copy into a network-isolated, disposable database and checks
its schema, ownership and question invariants; run the same drill with
`make verify-database-restore`.
Encrypted offsite replication has a fail-closed implementation and security runbook,
but remains deliberately inactive until a dedicated crypt remote, independent alert,
provider controls and offline recovery key satisfy the documented activation gates.

Operational deploy and rollback notes live in [docs/OPERATIONS.md](docs/OPERATIONS.md);
offsite gates and incident response live in
[docs/OFFSITE_BACKUP_RUNBOOK.md](docs/OFFSITE_BACKUP_RUNBOOK.md).

## API reference

| Method | Endpoint                      | Description                                                                          |
| ------ | ----------------------------- | ------------------------------------------------------------------------------------ |
| `GET`  | `/api/live/`                  | Process liveness; deliberately independent of PostgreSQL                             |
| `GET`  | `/api/health/`                | Readiness; returns 200 only if PostgreSQL is reachable                               |
| `GET`  | `/api/stats/`                 | Aggregate module/objective/difficulty coverage, without question or answer data      |
| `GET`  | `/api/search/`                | Search text/code with scope filters; no choices or answer metadata                   |
| `GET`  | `/api/daily/`                 | Stable five-question daily set spanning all four modules; no answer metadata         |
| `GET`  | `/api/quiz-set/`              | Random scoped set, ordered ID-targeted drill, or answer-safe full-mock preset        |
| `GET`  | `/api/questions/<id>/`        | Single question (choices only — no answer key)                                       |
| `POST` | `/api/questions/<id>/answer/` | Submit `{ "choice_id": N }`; returns correctness + the picked & correct explanations |
| `POST` | `/api/grade/`                 | Grade 1–100 unique questions; null choices count as unanswered                       |

## Project layout

```
backend/     Django project + DRF quiz app, management commands, tests
frontend/    React + Vite + Tailwind app
nginx/       Production vhost and security/proxy header snippets
scripts/     Atomic publishers, Nginx validation and public study-page generator
ops/         Reviewed systemd units for host-side operational jobs
.github/     CI and scheduled production-smoke workflows
docker-compose.yml
```

## License

[MIT](LICENSE) © Dragne Alexandru Mihai
