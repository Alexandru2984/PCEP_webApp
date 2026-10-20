# Production review — 2026-09-19

## 1. Production architecture discovered

The public request path is:

```text
Browser
  → Cloudflare edge
  → shared cloudflared systemd service and named tunnel
  → HTTPS on loopback system Nginx
      ├─ / and versioned assets → /var/www/pcep/frontend
      ├─ /practice/, sitemap, robots → /var/www/pcep/seo
      ├─ /static* and /media* → hardened retired-content 404
      ├─ /api/ → 127.0.0.1:8001
      │            → pcep_backend (Gunicorn, three workers)
      │            → pcep_db (PostgreSQL 16)
      ├─ /admin* and runner paths → hardened 404
      └─ exact /u/ collection routes → loopback Umami service

pcep-runner.micutu.com → static bridge, worker and Pyodide only
```

Cloudflared and Nginx are shared with other applications. The tunnel has explicit
routes for PCEP and another hostname plus a catch-all loopback TLS origin. PCEP
sets its reviewed Host/SNI and verifies the local Let's Encrypt certificate; the
legacy catch-all still disables verification for other hostnames. UFW exposes SSH
and the unrelated TURN service, but not ports 80/443. Nginx listens on 80/443 for
the local tunnel; the default TLS vhost redirects unknown hosts to
`https://micutu.com/`.
PCEP's backend port is bound only to `127.0.0.1:8001`; PostgreSQL publishes no
host port. The PCEP Docker bridge contains the backend and database.

Nginx terminates with a Let's Encrypt certificate and Cloudflare terminates the
public edge connection. The PCEP vhost accepts origins only from verified
Cloudflare address ranges or loopback. Nginx restores the verified client
address, replaces forwarding headers, and Django trusts exactly one proxy hop.

## 2. Critical findings

### P0

- Generated public study pages exposed every correct answer and every
  explanation without submission. The live pages and generator were backed up,
  replaced immediately, regenerated through the public serializer and covered
  by a regression test. Historical search-engine or third-party caches may
  retain the old content.

### P1

- `/api/grade/` accepted duplicate question IDs, so a client could count one
  question repeatedly. It now requires 1–100 unique positive 64-bit integer
  IDs, rejects ambiguous JSON values and foreign choices, and preserves order.
- Django 5.1.15 and DRF 3.15.2 had nine audited advisories; the Node tree had ten
  moderate/high findings. Django is now 5.2.17 LTS, DRF is 3.18.1, and both
  Python and npm audits report no known vulnerabilities.
- Public frontend requests could race, duplicate submissions and discard a
  recoverable exam after grading failure. Request guards, cancellation,
  timeouts, response validation and retry-safe exam state now cover these cases.
- Client-controlled forwarding chains could affect application throttling, and
  the public API accepted much larger bodies than its contract needs. Nginx now
  derives identity only from trusted Cloudflare peers, overwrites proxy headers,
  shares an IP rate zone across Gunicorn workers and caps API bodies at 64 KB.
- Django connected as the PostgreSQL bootstrap superuser, which unnecessarily
  extended an application compromise to cluster administration. New clusters now
  separate the bootstrap administrator from a non-superuser application owner;
  the same ownership split was restore-tested before production migration.
- Admin and seed paths could admit malformed question sets. Full inline
  validation, preflight seed checks and read-only live database auditing now
  enforce the four-choice/one-correct/explanation invariants.
- Pyodide startup and queues were unbounded and a failed worker could remain
  unusable. Startup, execution, source, queue and output bounds plus recreation
  after failure or timeout now preserve browser responsiveness.
- Frontend/static deployment deleted or exposed incomplete releases and did not
  preserve active-tab chunks. Releases now stage, validate and atomically swap;
  old chunks and a complete previous release are retained. Staged modes are
  normalized so Nginx can traverse and read sources created under mode 0700.

## 3. Security audit

Fixed controls include answer-key regression coverage across every public GET
endpoint and the generated SEO pages; `no-store` on every API response; strict
batch validation; bounded request bodies and rates; production fail-fast checks
for secret key and allowed hosts; secure cookies, HTTPS redirect and HSTS;
central headers and CSP; dotfile blocking; real missing-asset 404s; restricted
analytics proxy routes; fingerprinted Django admin static files; non-root
read-only backend execution; dropped Linux capabilities; `no-new-privileges`;
PID, memory and temporary-filesystem limits; and verified dependency downloads.
The production Python base is pinned by patch version and multi-architecture
digest, development/test files are excluded from its context, and CI now scans
the built OS and Python packages with a digest-pinned Trivy release. The runtime
stage also applies current Debian updates, closing the gap between a fixed Python
image digest and later security fixes from the distribution repositories.

The learner CSP no longer grants `wasm-unsafe-eval`; Pyodide runs on the dedicated
`pcep-runner.micutu.com` origin with a CSP restricted to its own static runtime.
Neither origin grants `unsafe-eval` or `unsafe-inline`. API responses use
`default-src 'none'`.
Workbox never stores API, answer, admin, study-page or analytics responses.
Browser progress import is schema-, type-, size- and count-bounded and never
contains an answer key.

Remaining security work:

- The public learner vhost now returns a cookie-free 404 for `/admin` and every
  `/admin/` path. A future operator interface belongs on a separate origin behind
  enforced phishing-resistant MFA and a tested emergency access procedure.
- Cloudflare currently injects a dynamic inline JavaScript-detection challenge.
  CSP blocks it, producing a console warning while leaving the application
  functional. Disable that edge feature rather than weaken CSP.
- The shared tunnel catch-all still uses `noTLSVerify` for unrelated hostnames.
  PCEP now bypasses it through an explicit hostname rule with a fixed Host/SNI and
  verified origin TLS. Completing the same migration for every other vhost belongs
  to those applications' deployment reviews.
- A partial database uniqueness constraint now prevents direct ORM or SQL writes
  from adding a second correct choice. The complementary cross-row rule requiring
  at least one correct choice is not a simple check constraint; Admin, seed/deploy
  audits and fail-closed API behavior continue to protect that case.
- DRF's memory throttle remains per process. The shared Nginx limit closes the
  production gap, but deployments that bypass Nginx must supply a shared cache.
- A full Trivy 0.75.0 scan reports 44 HIGH package occurrences across eight
  unique Debian 13 CVEs. None has a vendor-fixed version, none affects an
  installed Python package and there are zero CRITICAL findings. The current
  non-root, read-only, capability-free runtime limits exposure. Debian 12
  Bookworm was evaluated and rejected because the equivalent base reported 55
  HIGH and five CRITICAL findings, also without vendor fixes. CI blocks new
  fixable HIGH/CRITICAL findings; the unfixed set still requires periodic review.

No secrets were added to Git. A broad Docker process-inspection command surfaced
the database credential in session output; it was treated as exposed and rotated
immediately after the database runtime change. The replacement is 256-bit random
hex, the production `.env` and its protected rollback copy are mode 0600, and the
old value is no longer active. No database or Docker volume was deleted.

## 4. Backend changes

- Added pure `/api/live/` liveness while retaining DB-backed `/api/health/`
  readiness for container and monitoring compatibility.
- Reduced stats from four aggregate queries to one grouped query and exposed a
  bounded coverage matrix without question or answer data.
- Added strict grade/answer request serializers, deterministic error semantics,
  invalid-key 503 behavior, public `ids` filtering for targeted local drills and
  consistent cache/error middleware. Targeted drills preserve their validated ID
  order after filtering, so due and adaptive priority reaches the learner unchanged;
  ordinary quiz sets remain randomized.
- Added reusable question-bank validation, database-aware audit diagnostics,
  admin inline enforcement and safe seed preflight.
- Added a partial database uniqueness constraint that rejects multiple correct
  choices for one question even when a write bypasses Admin and model validation.
- Changed `seed_questions --update` to update choices in their existing order
  rather than delete and recreate them. Choice IDs used by saved local sessions
  now remain stable; a structural choice-count mismatch aborts the entire atomic
  update instead of partially reseeding the bank.
- Applied reversible question-content migrations in place without changing IDs.
  Earlier migrations removed equivalent and out-of-syllabus set questions. The
  latest replaces 19 questions that exercised language features absent from the
  official PCEP-30-02 objectives and removes four residual references from
  distractors or explanations. It preserves every question/choice ID and every
  correct-option position so saved sessions remain grade-compatible.
- Replaced the last two semantic duplicates with distinct list-slice deletion
  and dictionary add/delete exercises. Three high-similarity pairs remain as
  reviewed contrasts; exact prompt/code allowlisting makes any edit return them
  to the review queue. The strict source audit now has zero unreviewed candidates.
- Extended the AST-backed audit to reject set syntax, lambda expressions,
  `nonlocal`, `assert`, complex literals, dictionary comprehensions, starred
  unpacking, f-strings, `enumerate()` and `__name__` introspection. The same
  scope guard scans prompts, options and explanations for residual references.
- Added a reviewed primary PCEP-30-02 objective to every question. Module content
  digests prevent silent taxonomy drift; migration signatures fail closed on an
  unknown production row; a database constraint rejects cross-module objectives.
- Added answer-safe objective filters to quiz/search and objective aggregates to
  the existing one-query stats endpoint. All 15 objectives now have coverage.
- Added bounded database startup, connection health checks, short connect
  timeout, ManifestStaticFilesStorage, structured Gunicorn logs and request IDs.
- Marked successful internal Compose readiness probes and excluded only those
  loopback requests from Gunicorn access logs. Readiness failures and public
  requests using the same marker remain logged, preserving operational signal.

The bank now contains 308 questions and 1,232 choices. Four earlier questions
established coverage for previously empty objectives 1.1 and 1.2; three further
questions now cover the missing lexis, Python-keyword and instruction concepts
from those objectives. The original 305 questions and 1,220 choices were
byte-for-byte identical to the pre-release backup after migration, including
their IDs and explanations. The additive migration was also exercised through a
forward/rollback/forward cycle on a restored database copy. `order_by('?')`
remains: at 308 rows, it is simple and measured cost does not justify a more
complex sampler. Revisit it if the bank grows by orders of magnitude.

## 5. Frontend changes

Quiz execution now uses a reducer-backed session hook with explicit loading,
practice submission, exam grading, result and error transitions. Synchronous
guards stop double clicks; AbortController prevents stale responses from taking
over a new session; grading retry submits the same preserved answers.

Storage uses a versioned, bounded record with legacy migration and defensive
normalization. Corrupt, disabled or quota-limited storage shows a recovery
warning instead of crashing. Dashboard calculations include mixed sessions and
keep self-rated flashcards separate from graded accuracy.

Quiz setup, search, question cards, flashcards and review now expose the official
objective. Attempt history and the portable backup schema retain validated
objective breakdowns while accepting pre-taxonomy local data. Reports and the
dashboard identify the weakest objective and launch a precisely filtered drill.

Practice keyboard shortcuts now bind to the current session actions after every
state change. Selecting a confidence level and immediately answering with
`1`–`4` or `A`–`D` therefore records the chosen confidence instead of submitting
through a stale pre-selection callback.

Practice sessions now survive reloads with a strictly validated, local-only
snapshot. Recovery restores the current question, optional confidence and any
feedback already returned for submitted answers. Future questions are normalized
through the public-question whitelist, so their answer keys and explanations never
enter the snapshot. Resuming rotates ownership between tabs; stale tabs stop their
in-flight answer request and cannot overwrite or delete the active copy.

Completed Exam, Practice and Flashcard attempts now reuse their recovery ownership
ID as the history ID. The report opens only after both the atomic progress write and
matching recovery cleanup succeed. If cleanup fails after the write, retry recognizes
the existing attempt and clears recovery without incrementing history, mistakes or
study counters again.

The question-bank snapshot is now normalized before it reaches the setup UI.
Module, difficulty and objective totals must agree with both coverage matrices
and the four module summaries, so a partial or malformed API response produces a
recoverable error instead of crashing the workspace or clamping a quiz against
bad counts. A visible retry cancels any older stats request and preserves the
learner's setup choices.

The Pyodide manager bounds startup at 30 seconds, a run at eight seconds, source
at 20,000 characters, output at 10,000 characters and active/queued jobs at
four. Timeout or fatal failure replaces the complete cross-origin iframe and
worker. The pinned 0.29.4 npm tarball is verified by SHA-512 before staged
extraction. The resource controls are not a memory sandbox; the separate static
origin, private message capability and restrictive CSP contain JS-bridge access.
The manager also marks results as truncated when its independent character or
chunk bounds discard worker data, so defensive client-side truncation cannot be
mistaken for complete Python output.

## 6. UX/mobile changes

The mobile exam uses a collapsible five-column navigator with 44 px targets,
answered/flagged state, next-unanswered and next-flagged actions. Its timer stays
visible, uses a real deadline, gives one low-time announcement and prevents a
timer/manual-submit race. Submission confirmation wraps and restores focus;
failed grading keeps the attempt and offers retry.

The exam recovery screen follows that same wall-clock deadline while it remains open,
refreshes after browser suspension, switches expired attempts to a clear grading
action and requires confirmation before deleting the saved attempt.

Practice recovery uses the same explicit resume/discard pattern and remains usable
at 360 px. If the learner had already submitted the current answer, its feedback and
confidence return without another request; otherwise the unanswered card returns
cleanly. Flashcard recovery restores completed ratings and the current card, including
an answer only when it had already been revealed. All three recovery cards passed axe
checks.

Question and result headings receive focus after navigation. Code blocks scroll
without expanding the viewport. Actions, feedback, empty states, offline state,
storage failures and chunk failures now explain a useful recovery path. Manual
live screenshots at 1440 and 390 px confirmed clear desktop setup, practice
feedback and mobile exam navigation.

## 7. Accessibility

Added a skip link, semantic navigation controls, explicit pressed/expanded
states, labelled timer and output regions, polite status messages, visible focus,
dialog focus handling and global reduced-motion behavior. Shortcuts ignore text
entry, modifier/composition/repeat events and do not take over the code editor.
Keyboard help is available from every study screen.

Axe reports zero violations on setup, practice and exam in the deployed site.
The automated E2E suite also covers results, progress and flashcards in light
and dark themes. Horizontal-overflow checks pass at 1440, 1280, 1024, 768, 430,
390 and 360 px. This is strong regression coverage, not a claim of complete
assistive-technology certification.

## 8. New features

- Persistent local bookmarks and bookmark-only drills using fresh public data.
- Validated/versioned JSON progress export and import with preview and merge.
- Independent resets for history, mistakes and bookmarks.
- Mixed-session module and difficulty insights, strongest/weakest areas and
  accurate separation of flashcard self-ratings.
- Live question-bank snapshot and filter-aware available counts.
- Next-unanswered and next-flagged exam navigation.
- Online/offline, update-available, persistence-failure and app-error recovery UI.
- Browser-native PWA installation guidance with a tab-scoped dismissal and an
  explicit explanation of which study actions still require a connection.
- A focused end-of-session review queue combines misses with low-confidence correct
  answers and shows the learner's confidence and decision time beside each item.
- Flashcard reports use "Got it" / "Review later" recall language and never present
  self-ratings as a graded PCEP pass result; shared summaries also reflect the mode.
- Exam setup offers an exact PCEP-30-02 preset: 30 questions, a 40-minute absolute
  deadline and the official 7/8/7/8 module item distribution. Custom timed exams
  remain available, and the UI discloses the trainer's single-choice format limit.
- The bounded local attempt and backup schemas preserve the validated full-mock
  marker through crash recovery. Dashboard history then reports latest, best and
  passed full mocks separately from custom exams, without storing answer data.
- Focus-area drill actions from reports and preserved mistake drills.
- Fifteen-objective PCEP-30-02 filtering, coverage, attempt history and
  one-click weak-objective drills without exposing answer metadata.
- Reload-safe Practice sessions with post-submission feedback recovery, 24-hour
  expiry, strict schema validation and cross-tab ownership transfer.
- Reload-safe Flashcard decks with revealed-card recovery, answer-safe future cards,
  strict 24-hour snapshots and cross-tab ownership transfer.
- Due review sets can open as instant-feedback Practice or self-rated Flashcards; both
  fetch fresh public questions by ID, and the Flashcard path remains recoverable.

## 9. Performance

The stats endpoint now performs one grouped query. Questions prefetch choices;
no N+1 path was introduced. API payloads are capped and public answer data stays
minimal. Pyodide remains lazy but runs on a dedicated capability-free origin.
Hashed frontend/admin assets are
compressed and immutable; unversioned shell, worker, manifest and runtime entry
points revalidate. The current main production bundle is approximately 295.0 KB
JavaScript (91.4 KB gzip) and 47.0 KB CSS (8.5 KB gzip), excluding lazy chunks
and the Pyodide runtime.

The release process retains older lazy chunks so tabs open across deployment do
not fail. The service worker cleans old named caches and waits for the user to
reload after an update, avoiding an automatic mid-exam takeover.

The remaining database-side random ordering was measured on the live 308-question
PostgreSQL bank inside a read-only transaction. `ORDER BY random() LIMIT 50`
completed in 0.307 ms with 14 shared-buffer hits; a module+difficulty filtered
sample completed in 0.157 ms with 11 hits. The simple query is retained at this
scale and should be reconsidered only after bank growth or observed latency makes
its cost material.

## 10. Infrastructure

- **Nginx:** tracked production vhost, centralized headers/CSP, verified proxy
  headers, JSON request IDs/timing access logs without IP/query/cookie/auth data,
  privacy-suppressed rate-limit diagnostics, body and rate limits, compression,
  strict route caching, correct manifest/WASM/JS media types, missing-asset 404s
  and fail-closed retired static/media routes.
  Every reload followed `nginx -t`.
- **Release retention:** a read-only-by-default utility reports only exact
  frontend/static rollback and backup snapshots, enforces at least two retained
  copies and requires `--apply` before removal. Database/security backups cannot
  match its allowlist. No production snapshot was deleted during this work.
- **Cloudflare/Tunnel:** service is enabled and healthy. PCEP uses an explicit
  hostname ingress with verified loopback origin TLS; live cache behavior is
  BYPASS/DYNAMIC for shell/API/workers and immutable for hashed assets. No dashboard
  setting was changed because no Cloudflare account connector was available.
- **Docker:** backend runs as `appuser`, read-only, capability-free, bounded to
  512 MB/128 PIDs with a noexec 64 MB tmpfs and graceful stop. It exposes only
  loopback port 8001. Successful internal readiness probes are omitted from the
  access log only when their marker and loopback peer both match; failures and
  public probes remain logged. The pinned Python base receives current Debian
  security updates during the runtime build. PostgreSQL also runs non-root with a
  read-only root, no capabilities, `no-new-privileges`, 512 MB/128-PID bounds and
  bounded noexec runtime tmpfs mounts. It exposes no host port and keeps its external
  named PGDATA volume. Its digest-pinned PostgreSQL 16.15 Alpine image removes the
  unused root-only `gosu` helper; the resulting image has zero fixable HIGH/CRITICAL
  findings. A dedicated database-only environment file separates the bootstrap
  administrator credential from Django, while the application role owns only its
  database and public objects.
- **systemd:** Nginx, Docker and cloudflared are active. The weekly SEO generator
  remains installed as an existing systemd timer.
- **External monitoring:** a separate GitHub Actions workflow now performs a
  privacy-friendly public contract check every six hours and on manual dispatch.
  It is isolated from push/PR CI so an external outage cannot block code review.
- **PostgreSQL:** production connectivity/readiness and bank integrity pass. A
  compressed logical backup was made before deployment. No DB restart command
  was issued during this work; the DB container had been recreated by separate
  activity earlier in the session, so contents and hashes were explicitly
  rechecked.
- **TLS/firewall:** public HTTP redirects to HTTPS, edge/origin HTTPS works,
  HSTS is one year with subdomains/preload, and UFW has no public 80/443 rule.

## 11. Tests

Final validation on 2026-09-19:

- `make test` — backend 103 passed; frontend 90 passed; lint, format and build passed.
- `make audit` — seed audit clean; production and development Python audits clean;
  npm reported zero vulnerabilities.
- `make django-check` — passed.
- `cd backend && python -m pytest` — 103 passed.
- `DJANGO_SETTINGS_MODULE=pcep_project.test_settings python manage.py audit_questions --fail-on-warnings` — clean.
- Test-settings and live-container `manage.py check`; production
  `check --deploy --fail-level WARNING` — passed.
- `cd frontend && npm run test` — 90 passed across 16 files.
- `npm run lint`, `npm run format:check`, `npm run build` — passed.
- `npm run e2e` — 12 Playwright flows passed, including real Pyodide failure,
  timeout, output bound, recovery and offline reuse.
- `docker compose config --quiet`, isolated `scripts/check_nginx.sh` and live
  `sudo nginx -t` — passed.
- Live public validation — homepage, liveness, readiness, stats, quiz fetch,
  answer submit, grading, duplicate rejection, admin login, SEO pages, static
  assets, service worker, manifest, Pyodide files, headers, gzip, redirect and
  TLS passed. Pre-answer payloads and browser caches contained no answer data.
- Live Chromium — setup and practice fit all seven target widths; setup,
  practice and exam passed axe; 30 mobile exam targets were at least 44 px;
  service worker became ready; zero sensitive cache entries and zero application
  browser errors. Three Cloudflare-injected scripts were blocked by CSP as
  described above.

Continuation validation on 2026-09-26 covers 172 backend tests, 194 Vitest tests
and 24 Playwright flows. The release also passed both dependency audits, Django's
production deploy check, Compose/Nginx validation, a full migration/seed/audit on
a restored database copy, a scope-migration forward/rollback/forward cycle,
public answer-leakage probes and live Chromium at 390 and 1,440 px with zero axe
violations or horizontal overflow.

Continuation validation on 2026-09-27 covers 175 backend tests, 194 Vitest tests
and 24 Playwright flows. `make test`, lint, formatting, the production build,
strict seed and live-database audits, Django's deploy check, Compose validation
and live Nginx validation passed. Migration `0010` and both seed modes were
exercised on a fresh restore of the production backup; all 305 pre-existing
questions and 1,220 choices remained identical. Public probes confirmed the
three new questions expose only safe question/choice fields before submission,
while answer feedback remains available after submission. A subsequent frontend
release repeated all 194 Vitest and 24 Playwright checks and exercised the fixed
confidence-plus-keyboard flow against the public site at 390 px with no
application errors or horizontal overflow.

The stats-resilience release passes 201 Vitest tests and 25 Playwright flows.
Its live browser probe injected one 503 for `/api/stats/`, observed the recovery
message, retried against the real production API and rendered the validated 308
question snapshot at 390 px with no unexpected application errors or overflow.

The atomic-session release passes 204 Vitest tests, lint, formatting, the
production build and all 25 Playwright flows. Regression coverage verifies that
history, mistakes and review scheduling are written as one progress snapshot;
a simulated quota failure preserves the entire preceding snapshot while the
completed report remains available in memory.

The exam-recovery follow-up passes 205 Vitest tests, lint, formatting, the
production build and all 25 Playwright flows. A quota-failure regression proves
that a graded exam keeps its recovery snapshot until the combined progress
snapshot has been stored successfully.

The progress-tools and content-audit release passes 177 backend tests, 207
Vitest tests across 27 files, lint, formatting, production build and all 25
Playwright flows. Seed and live-database audits pass for 308 questions; Python
production/development and npm dependency audits report no known
vulnerabilities. Regression coverage verifies honest reset/export failure
states and rejects every unparsable Python snippet except the two exact reviewed
syntax-error teaching cases.

The same-origin Umami route remains intentionally enabled with Do Not Track and
query/hash exclusion. Adding Vite's `vite-ignore` marker identifies the classic
proxied script as an external build input; Vite removes the marker from output,
keeps `/u/script.js` intact and no longer emits the misleading bundle warning.
The three legacy persistent volumes are now declared external under configurable
names. Compose resolves to the existing database/static/media mounts without
warnings, and teardown cannot delete those volumes with `-v`.

The release-observability release passes 178 backend tests and 216 Vitest tests
across 28 files, plus lint, formatting, the production build and all 25
Playwright flows. Python production/development and npm dependency audits report
no known vulnerabilities. The backend candidate passed Django's deploy check,
had no pending migrations and audited all 308 live questions read-only before
replacement. Live probes then confirmed matching frontend/backend revision
`0d92a2d8a4a0`, zero pre-submission answer fields, successful answer and grading
requests, zero axe violations or horizontal overflow at 390 px, a no-store
service worker, valid Nginx/Compose configuration and no new backend errors.

The controlled-PWA-update follow-up passes 218 Vitest tests across 28 files,
lint, formatting, the production build and all 25 Playwright flows. Regression
coverage proves that a waiting worker is discovered without activating itself
and receives `SKIP_WAITING` only from the Reload action. The public generated
worker contains one message-gated skip call, one `clients.claim()` call and no
unconditional activation. Live Chromium confirmed the new release, an active
controller, zero sensitive cache entries, zero axe violations or horizontal
overflow at 390 px and a working offline reload.

The cross-version-storage follow-up passes 222 Vitest tests across 28 files,
lint, formatting, the production build and all 25 Playwright flows. Progress,
settings and active-exam snapshots with a newer schema are preserved across
stale-tab reads, writes and clears; the UI identifies the conflict on startup or
after a cross-tab storage event. A live transition probe kept the preceding app
shell loaded while the new worker entered `waiting`, confirmed no automatic
reload, and observed navigation only after the Reload action. Fresh live Chromium
then verified release `e8c15d24af42`, an active controller, zero axe violations
and no horizontal overflow at 390 px.

The active-exam ownership follow-up passes 226 Vitest tests across 28 files,
lint, formatting, the production build and all 26 Playwright flows. Every saved
exam now has a validated session ID; resume rotates it, stale-tab saves and
deletes fail, and pre-existing recovery data receives a compatible legacy ID.
The two-tab browser regression confirms that the former owner returns to the
recovery screen and announces the conflict. Fresh live Chromium verified release
`dc03ce0b8fbc`, ownership transfer on the public site, zero axe violations, no
horizontal overflow at 390 px and an active service worker with no waiting update.
Public API probes again found zero answer fields before submission and normal
feedback after submission.

The in-flight-grading follow-up passes 228 Vitest tests across 28 files, lint,
formatting, the production build and all 26 Playwright flows. A cross-tab owner
change now aborts any pending grading request, and a direct ownership check before
result persistence covers delayed or missed storage events. A live two-tab probe
held the first tab's grading request open while the second tab resumed the exam;
release `3714babc2946` returned the stale tab to recovery, preserved the new owner
and left local attempt history empty.

The progress-synchronization follow-up passes 232 Vitest tests across 29 files,
lint, formatting, the production build and all 27 Playwright flows. Setup counts,
the dashboard and bookmark state now react to same-tab writes and native cross-tab
storage events without polling. Note viewers refresh automatically; an editor
detects a newer stored note, preserves its draft and requires a second deliberate
Save before replacement. Fresh live Chromium verified release `76a10d5f0b14`, a
dashboard update after another tab completed a session, protected concurrent note
editing, zero axe violations and no horizontal overflow at 390 px.

The supported-dependency refresh keeps React 18, Vite 6 and Vitest 4 while
updating compatible frontend packages and moving the development linter from the
unsupported ESLint 9 line to ESLint 10. `npm ci`, 232 Vitest tests, lint,
formatting, the production build and all 27 Playwright flows pass; `npm audit`
reported zero vulnerabilities at that checkpoint. Axios remained exactly at 1.18.0
then because 1.20.0 alone increased the entry bundle by about 5.9 KB / 1.9 KB gzip
with no security finding to resolve. The validated entry remained 277.89 KB / 88.61 KB
gzip. Fresh live Chromium verified release `11d8c34b956e`, answer-safe quiz fetch,
post-submit feedback, zero axe violations, no mobile overflow and an active worker.

The supported Python dependency refresh moves DRF to 3.18.1,
`django-cors-headers` to 4.9.0, `psycopg2-binary` to 2.9.13, pytest to 9.1.1 and
pytest-django to 4.14.0 while retaining Django 5.2 LTS, Gunicorn 23 and
django-environ 0.11. The DRF 3.18 indexed nested-list error format is explicit
and regression-tested, and upcoming DRF removal warnings now fail the suite.
All 179 backend tests, both Python dependency audits, the 308-question audit,
Django's production deploy check and Compose validation pass. The candidate
image also passed deploy and migration checks before replacement. Public probes
verified release `3d00516c0af7`, readiness, pre-answer secrecy, post-answer
feedback and the indexed validation response; live Nginx validation passed.

The backend release workflow now enforces the recovery order that the dependency
rollout exposed: it verifies and tags the exact running image, creates and
validates a private atomic database dump, and only then allows a candidate build.
It checks the embedded revision, Django production settings and migration state
before replacement, then waits for health, confirms migrations, audits the live
bank and verifies the public revision. Pending migrations require an explicit
reviewed flag. Nine focused regressions cover ordering, image identity, dump
privacy/integrity, migration semantics and dirty-tree refusal; the complete
backend suite now passes 188 tests.

The container security follow-up pins Python 3.12.14's official image digest,
removes tests and development configuration from the runtime context and adds a
digest-pinned Trivy scan to the ops CI job. The exact candidate and deployed
images pass Django's production check and have zero fixable HIGH/CRITICAL OS or
Python findings. `actionlint`, Compose validation and the new Make target pass.
The first automated release attempt stopped before replacing production when its
candidate-revision probe lacked Django initialization; the live container stayed
healthy. The corrected probe is regression-tested, and the subsequent complete
release validated the rollback-first behavior end to end.

The CI supply-chain follow-up upgrades the official actions to their current
Node 24 majors and pins every `uses:` reference to a full release commit SHA.
Checkout credentials are no longer persisted because no job writes to Git.
`actionlint` passes, all workflow permissions remain read-only and adjacent
version comments preserve a reviewable update path.

The Practice-recovery follow-up passes 248 Vitest tests across 30 files, lint,
formatting and the production build. All 25 unaffected Playwright flows passed in
the full run; the three flows whose old refresh assumptions correctly encountered
the new recovery card were updated and passed targeted reruns, for 28 covered flows
in total. Browser coverage verifies post-submit feedback recovery, a clean next
question, no answer metadata in the stored public question list, mobile fit, axe and
existing exam ownership transfer.

The explanation-quality follow-up removes a dead, factually wrong draft that the
seed module used to replace in memory immediately after declaration. The final bank
is unchanged, but there is now one canonical source entry. Seed and database audits
also reject explanations shorter than 20 characters and strong editorial drafting
markers. All 189 backend tests, the 308-question seed audit, Django checks and a
read-only live database audit pass; the live bank already had zero violations.

The Flashcard reliability follow-up cancels a reveal request immediately on Quit or
unmount, ignores stale responses and validates the complete feedback schema before
React renders it. Invalid or incomplete feedback keeps the card hidden and retryable.
All 250 Vitest tests, lint, formatting and the production build pass. Playwright
passes the full Flashcard flow plus axe and horizontal-fit checks in both themes at
seven viewport widths.

The Search reliability follow-up replaces render-delayed loading state as the
duplicate-submit guard with the synchronous request ref. Two submissions in one
render now issue exactly one request instead of aborting the first and spending a
second API call. All 251 Vitest tests, lint, formatting and the production build pass;
the answer-safe mobile Search-to-drill Playwright flow also passes.

The Flashcard keyboard follow-up restores focus after the asynchronous Reveal button
is removed, publishes `aria-keyshortcuts` and adds Space/Enter reveal plus `1`/`2`
self-rating controls. The visible shortcut guide matches the actual bindings. All 252
Vitest tests, lint, formatting and the production build pass. Browser coverage uses
the shortcuts end to end and the Flashcard screens remain axe-clean without overflow
in both themes across seven viewport widths.

The Flashcard recovery follow-up stores a strictly normalized 24-hour deck snapshot,
resumes completed ratings and an already revealed current card, and rotates ownership
between tabs. Unrevealed questions retain only the public API fields. Quit, confirmed
discard and successful completion clear only the current owner's copy, while stale
tabs return to recovery and cannot overwrite it. All 269 Vitest tests across 31 files,
lint, formatting, the production build and all 29 Playwright flows pass. The browser
regression covers reload without a duplicate answer request, answer-key boundaries,
mobile fit, axe, advancement after resume and cleanup on Quit.

The due-Flashcard follow-up lets the learner choose Practice or Flashcards for the
same bounded, local review schedule. Both paths fetch fresh public questions by ID;
the Flashcard path immediately receives the existing answer-safe recovery and
cross-tab ownership behavior. All 270 Vitest tests across 31 files, lint, formatting,
the production build and all 29 Playwright flows pass. Browser coverage opens the due
deck in a second tab, verifies public payload and snapshot secrecy, axe and mobile fit,
cleans up on Quit, then confirms adaptive Practice still launches normally.

The saved-list Flashcard follow-up gives mistakes and bookmarks the same Practice or
Flashcards choice. Both modes fetch fresh public questions by bounded local IDs, and
Flashcards inherit strict recovery, stale-tab ownership and answer-key boundaries.
All 274 Vitest tests across 31 files, lint, formatting, the production build and all
29 Playwright flows pass. Browser coverage exercises bookmark persistence, both drill
modes, the answer-safe API payload and recovery snapshot, axe and mobile overflow.

The Search Flashcard follow-up lets a learner launch selected answer-safe search
results as Practice or Flashcards. Both paths refetch current public questions by
the selected IDs; the Flashcard path receives the existing recovery, validation and
cross-tab protections. All 275 Vitest tests across 31 files, lint, formatting, the
production build and all 29 Playwright flows pass. The mobile browser flow verifies
both the search preview and selected deck payloads, the recovery snapshot, axe and
horizontal fit without exposing answer metadata.

The adaptive-Flashcard follow-up exposes the same explainable ranked study set as
graded Practice or self-rated Flashcards. Both paths request the exact bounded local
IDs and receive fresh public questions, while Flashcards retain the validated
answer-safe recovery and cross-tab ownership behavior. All 276 Vitest tests across
31 files, lint, formatting, the production build and all 29 Playwright flows pass.
Browser coverage verifies the ranked request, public payload and recovery secrecy,
both launch modes, axe and mobile horizontal fit.

The targeted-order follow-up fixes a server-side mismatch that randomized every
`ids` drill after the browser had ranked it. The API now restores the validated
request order after optional filters and applies `count` to that order, while
unscoped quiz sets retain database randomization. All 197 backend tests pass,
including two-query prefetch coverage, filtered-order and answer-leakage regressions;
the 308-question audit and Django production check also pass. Playwright's API mock
now implements the same ordered-ID and `count` contract, and the adaptive browser
flow asserts that Practice, Flashcards and the recovery snapshot all retain that
order. All 29 Playwright flows, lint and formatting pass.

The production-monitoring follow-up adds a standard-library-only, read-only smoke
check for the public shell, its fingerprinted JS/CSS entry assets, service worker,
liveness, database readiness, release and request markers, security/cache headers,
fully reconciled module/objective/difficulty matrices, strict answer-safe random,
daily, detail and search payloads, and exact targeted-drill
order. Requests use TLS validation, bounded two-megabyte responses, a 20-second
timeout and three attempts; no write, answer or grade endpoint is called. All 209
backend tests pass, including twelve focused smoke-contract regressions. The live
command verified backend release `7207b1bc2fb9`, 308 questions, two entry assets
and an exact three-question targeted order; the pinned scheduled workflow passes
`actionlint` without network access.

The focused-review follow-up turns the existing report queue into an immediate
Practice or Flashcard action. It preserves session order, refetches current public
questions by ID and reuses the validated recovery schemas, so missed and
low-confidence-correct items never become a stored answer bank. All 279 Vitest tests,
lint, formatting, the production build and all 29 Playwright flows pass. Browser
coverage verifies exact `[1, 2]` request/response/recovery order and answer secrecy;
the report remains axe-clean and mobile-fit.

The safe-quit follow-up fixes Practice and Flashcard controls that cleared an active
recovery snapshot immediately. Both now require an explicit native confirmation;
cancelling keeps the active request, screen and stored recovery intact, while
confirming aborts pending Flashcard work before cleanup. Seven targeted component
tests and all four affected Playwright flows pass alongside lint, formatting and a
fresh production build.

The targeted-list follow-up removes an inconsistent frontend-only 50-question cap.
Saved mistakes, bookmarks and review queues now preserve up to 100 unique IDs in
their intended order, matching the existing API and recovery contracts. A regression
uses a duplicate ahead of a 100-question list to prove deduplication happens before
the bound and that the final question is retained. All 279 Vitest tests, lint,
formatting and the production build pass.

The quick-session follow-up adds a five-question size to custom Practice, Exam and
Flashcard setup. Unlike the deterministic daily challenge, it remains random and
honors the selected module, objective and difficulty. The count selector is now a
semantic fieldset with explicit accessible button names, 44 px minimum targets and
a five-column mobile grid. All 280 Vitest tests pass; the full browser coverage plus
the corrected focused flow account for all 29 Playwright scenarios, including the
new `count=5` request and horizontal fit at 360 px.

The session-preference follow-up fixes a capped scope silently replacing the learner's
chosen quiz size. Setup now sends and persists the requested size, while the existing
validated response continues to define the actual session length and exam deadline.
Returning from a one-question scope therefore restores the chosen 5/10/20/30/50
option instead of an impossible unselected `Questions: 1` state. All 281 Vitest tests,
lint, formatting and the production build pass.

The legacy-session-size follow-up repairs browsers that already stored one of those
unsupported setup values before the preceding fix. Setup normalizes unsupported
preferences to 30 on read without rewriting localStorage, while active recovery keeps
its separate 1-through-100 actual-length contract. Unit and component regressions
cover both the storage boundary and the selected setup control. All 283 Vitest tests,
lint, formatting, the production build and the focused 360 px Playwright flow pass.

The feedback-integrity follow-up closes a frontend trust-boundary gap shared by all
three study modes. Feedback is now bound to the requested question and selected
choice, its correctness flag must agree with the returned correct choice, explanation
fields are required, undocumented fields are rejected and only a canonical four-field
object reaches session state. Contradictory Practice feedback leaves the question
retryable and records no attempt. All 293 Vitest tests across 32 files, lint,
formatting, the production build and all 29 Playwright flows pass.

The search-consistency follow-up invalidates results as soon as the learner edits the
query. It aborts an in-flight request, clears the old selection and ignores a late
response, preventing a drill built for one term from appearing under another. Scope
changes retain their existing keyed remount and cancellation boundary. All 294
Vitest tests across 32 files, lint, formatting and the production build pass; the
answer-safe mobile Search-to-Flashcards Playwright flow passes with the new refresh.

The quiz-load-recovery follow-up gives an initial Practice, Exam, Flashcard, daily,
full-mock or targeted request a direct Retry from the error screen. The retry reuses
the exact validated setup instead of asking the learner to reconstruct it, while Back
to setup remains available. Recovery storage is still created only after a valid
answer-safe question set arrives. All 294 Vitest tests across 32 files, lint,
formatting, the production build and all 30 Playwright flows pass. Mobile browser
coverage forces the first request to return 503, verifies the exact module,
difficulty and count on retry, and checks answer-safe recovery plus horizontal fit.

The exam-review-integrity follow-up fixes a regression introduced when grading
feedback became canonical. The canonical object deliberately drops echoed request
identifiers, so completed exams now retain the selected choice from the already
validated local grading payload. Correct answers no longer appear as skipped when
the learner opens the full review, while unanswered questions remain explicitly
skipped. All 294 Vitest tests across 32 files, lint, formatting, the production build
and all 30 Playwright flows pass. Browser coverage grades through a throttled retry,
opens all four results and verifies four correct selections with zero skipped labels.

The frontend-asset-retention follow-up bounds release-root growth without making an
open tab depend on the new build. Publication keeps hashed chunks from the last seven
days and always keeps every chunk built with the immediately previous entry assets,
even after a long quiet period. Expired generations are omitted only from the atomic
staging root; the full previous root and external backup remain rollback copies. The
window is configurable from 1 through 365 days. The production plan currently keeps
196 of 318 assets and expires 122 historical chunks (about 6 MB). All 211 backend
tests and the Django production check pass; regressions cover an old previous build,
its lazy chunk, a recent chunk, one expired generation and invalid configuration.

The cancellable-quiz-loading follow-up gives a slow initial question request a visible
44 px Cancel loading action. Cancellation aborts the request, returns immediately to
setup and preserves the selected preferences. The existing request-identity guard
prevents a late response from starting a session or writing active recovery. All 294
Vitest tests across 32 files, lint, formatting, the production build and all 31
Playwright flows pass. The mobile regression keeps the mocked response pending for
five seconds, cancels from an axe-clean loading screen and confirms the late response
cannot move the app away from setup or create a Practice recovery record.

The access-log signal follow-up removes the successful readiness probe emitted every
ten seconds from routine Gunicorn access logs. Suppression requires the exact health
path, GET, a successful response, the Compose-only marker and a loopback peer. Failed
readiness checks and public requests remain logged. All 214 backend tests, the strict
308-question audit, Django's production deploy check, Compose rendering, entrypoint
syntax and Gunicorn configuration loading pass.

A refreshed vulnerability database found seven fixable HIGH package occurrences in
the first access-log candidate: one PCRE issue and two OpenSSL issues repeated across
the installed OpenSSL packages. The pinned upstream Python image had not yet been
rebuilt with Debian's `u3` packages. The runtime now applies current Debian updates;
the replacement candidate contains `libpcre2` 10.46-1~deb13u3 and OpenSSL
3.5.7-1~deb13u3. The blocking Trivy scan reports zero fixable HIGH/CRITICAL OS or
Python findings, while the full report retains the same 44 unfixed HIGH occurrences
across eight Debian CVEs and zero Python findings. All 214 backend tests pass.

The backend deploy workflow now resolves the newly built candidate to its immutable
Docker image ID and runs the blocking Trivy audit before `docker compose up`. A
vulnerability finding, scanner outage or invalid candidate ID therefore stops after
the already safe rollback snapshot and database backup, leaving the live container
untouched. The ordering and failure boundary are regression-tested; all 215 backend
tests, the question audit, Compose rendering and Django deploy check pass.

The quiz-set response-boundary follow-up rejects a count that disagrees with the
payload, more questions than the learner requested, a foreign targeted ID or a
targeted list whose order changed. Ordered subsets remain valid so deleted legacy
bookmarks do not block the rest of a drill. Invalid responses create neither active
recovery nor progress. All 299 Vitest tests across 32 files, lint, formatting and the
production build pass.

The digest-pinned container scanner is updated to Trivy 0.75.0. Its blocking scan
of the immutable backend image currently in production reports zero fixable
HIGH/CRITICAL findings. A full scan independently confirms the documented 44 HIGH
package occurrences across eight unfixed Debian CVEs, zero Python findings and zero
CRITICAL findings.

Progress import now treats each file read as an ordered request. When two browser
reads finish out of order, only the most recently selected backup can set the
preview, loading state or error. The progress tools expose the active validation as
an accessible status and busy state. A deferred-file regression test reproduces the
race; all 300 Vitest tests across 32 files, lint, formatting and the production build
pass.

The first live mobile validation also exposed a skipped heading level on an empty
Progress dashboard: the standalone backup section used an `h3` directly after the
application `h1`. It now uses the same top-level `h2` hierarchy as the populated
dashboard. The backup Playwright flow runs axe on this exact empty state, and the
component test pins the heading level.

The two full-theme accessibility matrices each navigate every study mode, run axe
repeatedly and check seven viewport widths. Under concurrent host load they reached
the suite's generic 30-second timeout without a failed assertion; isolated runs
passed. Their timeout is now scoped to 60 seconds while retries and all assertions
remain unchanged. The final two-worker run completed them in 25.8 and 24.9 seconds,
and all 31 Playwright flows passed.

A later dependency audit reported new HIGH-severity Axios findings affecting the
pinned 1.18.0 release. Axios is now pinned to the fixed 1.20.0 release with a fresh
registry lock integrity value. The measured cost is about 5.9 KB uncompressed / 1.8
KB gzip on the entry bundle, which is warranted now that it closes an active finding.
`npm ci` reproduces the tree, `npm audit --audit-level=moderate` reports zero
vulnerabilities, and all 300 Vitest tests, lint, formatting, the production build
and 31 Playwright flows pass against the new client.

Production smoke now verifies the independently deployed frontend identity instead
of reporting only the backend revision. Vite injects exactly one bounded static
release marker into the shell and rejects an invalid build identifier; the existing
footer continues to show the same value. The smoke contract validates and reports
that marker separately from `X-PCEP-Release`. Missing, development, malformed and
duplicate markers are regression-tested; all 216 backend tests pass.

The Axios advisory appeared after the previous dependency-clean release, exposing
a monitoring gap: push/pull-request audits do not run while a repository is idle.
A separate daily and manually dispatchable workflow now audits both Python
requirement sets and the npm lockfile. It has read-only repository permissions,
ten-minute job limits, SHA-pinned official actions and disables npm package scripts
during tree reproduction. The current production/development Python audits and
`npm audit --audit-level=moderate` all report zero known vulnerabilities. The npm
install emits a deprecation notice for Workbox's transitive `glob@11.1.0`, but the
package has no active audit finding; forcing a PWA dependency replacement solely
for that warning would add unjustified release risk.

Session completion previously entered the report even when the atomic progress write
failed. Although its active recovery record remained, leaving the report could then
clear that last copy, and the final Flashcard rating stayed guarded against a second
click. Completion now fails closed in Practice, Exam and Flashcards: it keeps the
current screen and active recovery record, explains the failure and makes the exact
completion action retryable. The attempt is shown as complete and recovery is cleared
only after the combined progress snapshot succeeds. All 302 Vitest tests, lint,
formatting, the production build and all 31 Playwright flows pass, including the
throttled-grading retry contract.

Live validation of that recovery path found the global persistence warning still
visible after the retry had successfully stored progress. Successful storage writes
now emit a recovery signal consumed by the runtime status banner, while failed writes
continue to emit the existing warning. The browser-level offline/storage recovery
flow and a component regression pin both transitions. All 303 Vitest tests, lint,
formatting and the production build pass; the focused Playwright recovery flow also
passes.

Public header comparison found that normal API responses carried the restrictive API
CSP while Nginx-generated 413 and 429 JSON responses did not. The named error
locations now add `default-src 'none'; frame-ancestors 'none'` alongside the existing
no-store and common security headers. The isolated tracked-vhost check and privileged
live `nginx -t` pass. A controlled 70 KB request returned the same 413 JSON contract
with the new CSP after a graceful reload; public smoke and all runtime health checks
remained green.

The first warning-recovery implementation treated every successful localStorage write
as recovery for every failed write. Exam and Flashcard rerenders can persist a smaller
active-session record after the larger combined progress snapshot is rejected, which
could prematurely hide the global warning. Storage events now identify their key and
the runtime tracks the outstanding failed-key set. Successful removal also resolves
only its own key. Component and browser regressions prove that an active-session write
cannot clear a `pcep.progress` warning and that the later progress retry can. All 303
Vitest tests, lint, formatting, the production build and the focused Playwright flow
pass.

## 12. Commits

- `e71a8d7` — production discovery, baseline and prioritized plan.
- `6d2a450` — remove answer keys from public study pages.
- `7bfe21a` — update audited Django/DRF/Node dependencies.
- `4f0c502` — validate grading inputs and prevent feedback caching.
- `93c5db9` — enforce question integrity and label the blank option.
- `f13e9bf` — guard quiz requests and preserve failed exams.
- `96486e3` — add bookmarks, progress portability and mixed-session insights.
- `9d2f68e` — bound and recover the Pyodide worker.
- `5852ac2` — harden Nginx proxy trust, limits, routes and headers.
- `0a30092` — improve mobile exam, accessibility and recovery UX.
- `8cdf9ce` — isolate PWA caches and make updates session-safe.
- `7c102d5` — harden backend container and database startup.
- `9efb576` — add atomic releases and stronger CI validation.
- `6653dc7` — fingerprint production Django admin assets.
- `deb1040` — preserve public readability during atomic swaps.
- `de47bec` — serve the web manifest with the correct media type.
- `2504a0a` — synchronize production architecture and review.
- `69cd630` — resume interrupted exam sessions safely.
- `24ef2bc` — add the scheduled review engine.
- `45e27a2` — add transparent adaptive practice.
- `f089220` — add study momentum insights.
- `fa72eb8` — return new-quiz actions to setup.
- `1c2291e` — detect and replace a semantic duplicate.
- `b51789b` — detect equivalent practice items.
- `f419d4d` — add answer-safe question-search drills.
- `55df548` — contain search previews on mobile.
- `c17b5f3` — add bounded private personal notes.
- `f1c5826` — add confidence and response-time insights.
- `aec7817` — add the answer-safe daily challenge.
- `b5f859f` — add PWA install guidance.
- `d4305dd` — add focused answer review.
- `5462959` — distinguish flashcard self-ratings.
- `cfeffa1` — add the exact PCEP full-mock preset.
- `3389750` — track full-mock progress.
- `dcb7cbf` — harden saved-attempt recovery.
- `13325ea` — add safe release-retention previews.
- `01d477d` — replace out-of-syllabus set questions.
- `ed2b6b6` — add the audited syllabus-objective taxonomy.
- `64613ad` — add objective-level practice and insights.
- `bd920f3` — record the objective-taxonomy production release.
- `df2171e` — align the reviewed question bank with PCEP-30-02 scope.
- `ea97ef0` — replace the remaining reviewed semantic duplicates.
- `e5df6eb` — record the question-quality cleanup release.
- `e7d7840` — preserve choice IDs during seed updates.
- `5ccb595` — expand foundations coverage for objectives 1.1 and 1.2.
- `92808fe` — record the foundations coverage release.
- `4d90431` — keep keyboard-submitted confidence metadata current.
- `bb9b04c` — record the keyboard-confidence frontend release.
- `493d368` — validate and retry question-bank stats snapshots.
- `245ef3c` — record the stats-resilience frontend release.
- `fffea9e` — persist each completed session as one atomic progress snapshot.
- `410efa6` — record the atomic-session frontend release.
- `a6ecdd3` — retain exam recovery when final progress cannot be persisted.
- `c85c291` — record the exam-recovery frontend release.
- `e33e5fd` — report progress reset and export failures accurately.
- `7a5e4dd` — reject unreviewed invalid Python snippets during content audits.
- `1caacf5` — record the progress-tools and content-audit production release.
- `389962e` — mark the same-origin analytics script as an external Vite input.
- `ee424e5` — protect persistent Docker volumes as externally managed data.
- `f9da41f` — record the analytics and external-volume hardening release.
- `0d92a2d` — expose validated frontend and backend release revisions.
- `e36ffd8` — record the release-observability deployment.
- `4969d39` — activate PWA updates only after the learner requests reload.
- `3e030b3` — record the controlled PWA update release.
- `e8c15d2` — preserve local data written with a newer storage schema.
- `ed5e2eb` — record the cross-version storage release.
- `dc03ce0` — prevent stale tabs from overwriting active exams.
- `ca59a7a` — record the active-exam ownership release.
- `3714bab` — cancel stale cross-tab grading before it can persist.
- `ae3c5c0` — record the cross-tab grading release.
- `76a10d5` — synchronize progress UI and protect concurrent note drafts.
- `1ae62bd` — record the progress synchronization release.
- `11d8c34` — refresh supported frontend dependencies and ESLint 10.
- `f239514` — record the frontend dependency release.
- `3d00516` — refresh supported Python dependencies and pin the DRF error contract.
- `2aa0bf7` — record the backend dependency release.
- `98db7a9` — automate rollback-safe backend releases.
- `19754d5` — record rollback-safe backend releases.
- `5085601` — pin and scan the backend runtime image.
- `9d8ad66` — initialize Django for exact candidate revision checks.
- `26ba462` — record the container security release.
- `2040b48` — pin CI actions and stop persisting checkout credentials.
- `94c6291` — resume interrupted Practice sessions without leaking future answers.
- `d21757e` — document Practice recovery and its storage boundary.
- `e8fc01e` — reject short/editorial explanations and remove a dead draft question.
- `8026db9` — document the explanation quality gates.
- `20453df` — cancel stale Flashcard reveals and reject malformed feedback.
- `698aed9` — document resilient Flashcard reveal behavior.
- `c7a7fb6` — prevent duplicate Search requests in the same render.
- `afcb584` — document the Search request guard.
- `89eb12b` — record the Search reliability release.
- `02b23e0` — add focus-safe Flashcard keyboard self-rating.
- `555d4ab` — document Flashcard keyboard controls.
- `a2b0549` — record the Flashcard keyboard release.
- `3ddd657` — add the validated Flashcard recovery schema.
- `072de44` — resume interrupted Flashcard study sessions.
- `b5b4c4c` — document Flashcard session recovery.
- `3173277` — record the Flashcard recovery release.
- `1b7602c` — add due-review Flashcard decks.
- `e2dc67e` — document scheduled Flashcard reviews.
- `571f010` — enforce shared question-quality rules in Django Admin.
- `5a6a74d` — document the Admin question-quality gates.
- `b94a760` — record the Admin question-quality release.
- `1b311cb` — add Flashcard drills for mistakes and bookmarks.
- `ba41841` — document saved-list Flashcard drills.
- `4bf62b3` — record the saved-list Flashcard release.
- `49f31ee` — add Flashcard mode to selected Search drills.
- `bb77e0d` — document Search Flashcard drills.
- `8c5b78d` — record the Search Flashcard release.
- `64862bd` — add adaptive Flashcard sessions.
- `e4568e2` — document adaptive Flashcard sessions.
- `ba13b7a` — record the adaptive Flashcard release.
- `0091bc7` — preserve targeted study order in the API.
- `7207b1b` — document ordered targeted drills.
- `494b862` — add privacy-friendly scheduled production monitoring.
- `5d1ff63` — document scheduled production smoke checks.
- `840d042` — add one-click focused review drills.
- `9a101c9` — confirm before discarding active study sessions.
- `c9e084a` — document focused review and safe session exit.
- `eb38ca4` — cover every answer-safe public endpoint in production smoke checks.
- `961670f` — document complete public smoke coverage.
- `a7550b4` — record measured database randomization cost.
- `757ee0c` — preserve complete targeted drill lists.
- `5bb2313` — document complete targeted study lists.
- `e8cc50d` — add quick five-question sessions.
- `394106b` — document quick study sessions.
- `cc26d3a` — preserve the learner's preferred session size.
- `a4d088d` — document stable session-size preferences.
- `b65f5dc` — migrate unsupported legacy quiz-size preferences.
- `5ebac4c` — document legacy quiz-size migration behavior.
- `4925f47` — reject inconsistent or unscoped grading feedback.
- `6347f25` — document strict frontend feedback validation.
- `9d01aa2` — invalidate stale question-search results.
- `b9cc1f4` — document search result invalidation.
- `2a92ee7` — retry failed quiz loads with the exact saved setup.
- `895bc22` — document recoverable quiz loading.
- `31718b7` — preserve submitted Exam choices in completed review.
- `1b4414f` — document accurate Exam review choices.
- `dc371dc` — bound retained frontend asset generations.
- `217ead0` — document bounded frontend assets.
- `a4b133c` — cancel slow quiz loads without accepting late responses.
- `661f605` — document cancellable quiz loading.
- `22ec56a` — suppress only successful internal readiness probes in access logs.
- `a9b5c67` — document internal healthcheck log filtering.
- `5244b9d` — apply current Debian security patches in the runtime image.
- `0ae831c` — record the runtime package remediation.
- `fc10228` — scan each immutable backend candidate before replacement.
- `2915c62` — document the pre-replacement image gate.
- `d3c5585` — validate quiz-set counts and targeted response scope.
- `443dcb8` — document strict quiz-set response validation.
- `0f5cf62` — update the digest-pinned Trivy scanner to 0.75.0.
- `3f30e8e` — keep stale backup reads from replacing a newer selection.
- `775a165` — document resilient progress imports.
- `d6cb023` — preserve heading order on an empty Progress dashboard.
- `abb4876` — document the Progress heading correction.
- `ed24b7b` — give the full accessibility matrices a measured timeout budget.
- `5e8ebbc` — record the resilient Progress frontend release.
- `85098b0` — update Axios to the fixed 1.20.0 release.
- `6a2b681` — document the Axios security remediation.
- `d4ddf83` — verify frontend and backend release identities independently.
- `4c1342b` — document frontend release identity checks.
- `6b49fee` — record the frontend identity release.
- `0895af0` — route PCEP through verified Cloudflare Tunnel origin TLS.
- `e72a4f4` — run dependency advisory audits daily and on manual dispatch.
- `943a98b` — keep failed completed-session snapshots recoverable and retryable.
- `4064106` — document recoverable completion behavior and validation.
- `a8c7cb6` — clear a stale persistence warning after storage recovers.
- `a4823b8` — document the storage-warning recovery contract.
- `1992145` — align Nginx-generated API error CSP with normal API responses.
- `5a6c92a` — keep storage warnings scoped to the key that failed.
- `6b4ddc8` — document key-scoped storage recovery behavior.
- `c11c6d9` — verify generated Nginx API error contracts in isolated CI.
- `4bbeaea` — prevent multiple correct choices at the database boundary.
- `9ab7724` — report Pyodide output truncated at the manager boundary.
- `57fb43c` — make completed-session cleanup retry-safe and idempotent.
- `c917fa6` — harden and continuously verify the PostgreSQL container runtime.
- `26b72ae` — separate PostgreSQL administrator and Django application roles.

No commit was pushed by the engineering assistant, and no authorship, co-author or
generated-by attribution was added.

## 13. Remaining opportunities

1. If an operator UI becomes necessary, place it on a separate origin behind
   Cloudflare Access and phishing-resistant MFA, after verifying an emergency
   procedure to avoid lockout. Never republish it on the learner origin.
2. Disable or correctly scope Cloudflare JavaScript detection, then repeat the
   public console/CSP check. Review the dashboard's cache rules and tunnel
   hostname ownership directly.
3. Add finer concept tags only with a controlled vocabulary and coverage audit.
   Official-objective filters and weak-area reports now cover the stable syllabus
   layer; current adaptive ranking remains deliberately explainable through
   performance, due-date, confidence and difficulty signals.

## 14. Deployment notes

Question-content migrations through `0010_add_foundations_coverage` are applied.
The latest additive migration created exactly three questions and twelve choices;
its no-op reverse keeps those valid study records on rollback. Both normal and
`--update` seed modes were then verified as idempotent on a restored copy. The
backend image was rebuilt, and only the backend service was recreated. This
release did not publish frontend/static files and did not reload Nginx. No new
required production environment variable was introduced.

Backups and rollback artifacts are under
`/home/micu/backups/pcep/security-20260918`; the verified database backup is
`pcep_db_20260918-233147.sql.gz`. Retained backend rollback tags include
`pcep-backend-rollback:20260918` and
`pcep-backend-rollback:20260919-pre-manifest`. The objective release additionally
has verified backup `pcep_db_pre_objectives_20260926T201657Z.sql.gz`, rollback tag
`pcep-backend-rollback:20260926-pre-objectives`, and frontend release
`.frontend.previous-20260926T201930Z-836b615c`. The scope-alignment release has
verified backup `pcep_db_pre_scope_review_20260926T204219Z.sql.gz` (SHA-256
`99165443c29270a20d7d1d999dc7cbd34cff6cfb343860d00cf77ad372555133`) and rollback
tag `pcep-backend-rollback:20260926-pre-scope-review`. Previous frontend/static
release directories remain next to their live targets. The duplicate-cleanup
release has verified backup
`pcep_db_pre_near_duplicate_cleanup_20260926T205313Z.sql.gz` (SHA-256
`ca3be1b7be9380711e9b3af7f256ae4a5837965ba0ae9e6b3f769b2c3474d1bc`) and rollback
tag `pcep-backend-rollback:20260926-pre-near-duplicates`. Detailed commands and
cautions are in `docs/OPERATIONS.md`. The foundations release has verified
backup `pcep_db_pre_foundations_20260927T130359Z.sql.gz` (SHA-256
`4962c68e7236c6e899eda9bf9eede74f8e0fd17b70a2f7c04bfb09e1f509432e`), rollback
tag `pcep-backend-rollback:20260927-pre-foundations`, and candidate tag
`pcep-backend-candidate:5ccb595`. The keyboard-confidence frontend release has
rollback root `.frontend.previous-20260927T134217Z-3eb500a8` and external backup
`frontend.20260927T134217Z-3eb500a8`; both old and new hashed entry chunks were
verified publicly after the atomic swap. It required no backend restart, database
change or Nginx reload. The stats-resilience frontend release has rollback root
`.frontend.previous-20260927T135508Z-dd77b23c` and external backup
`frontend.20260927T135508Z-dd77b23c`; the new and preceding hashed entry chunks
were both verified publicly. It also required no backend restart, database
change or Nginx reload. The atomic-session release has rollback root
`.frontend.previous-20260927T140411Z-f2512df3` and external backup
`frontend.20260927T140411Z-f2512df3`. The published entry chunk
`index-CRCXmYW7.js` matches the validated build by SHA-256
(`0d725ef4d7c105df85404ebc8cffd3e0c162ef7a38e67880c0deda351977a9f2`), while
the preceding entry chunk remains publicly available for open tabs. Public and
origin homepages, readiness, the 308-question stats snapshot, redirect, security
headers, immutable asset caching and no-store service-worker caching were
verified. This release required no backend restart, database change or Nginx
reload. The exam-recovery follow-up has rollback root
`.frontend.previous-20260927T140817Z-98b02c88` and external backup
`frontend.20260927T140817Z-98b02c88`. Its entry chunk `index-DUQElxwR.js`
matches the validated build by SHA-256
(`10e12e0a209a253c8ed1ffffb9c6564bc871d7dadcc196abf0c4251860932b73`), and the
preceding chunk remains public. Public/origin homepages, readiness, the
308-question snapshot and service-worker cache policy passed after publication;
both containers stayed healthy. No backend restart, database change or Nginx
reload was required. The progress-tools/content-audit release has frontend
rollback root `.frontend.previous-20260927T141722Z-7a254166` and external backup
`frontend.20260927T141722Z-7a254166`. Its entry chunk `index-kkG5iDqv.js`
matches the validated build by SHA-256
(`2faee9bc9f70e97031d7204825033d8352c022c1d729f063abb207e478786dee`). The
previous backend image is tagged
`pcep-backend-rollback:20260927T141628Z-pre-syntax-audit`; the verified database
backup is `pcep_db_pre_syntax_audit_20260927T141628Z.sql.gz` with SHA-256
`7579fb8a3ef20fbe5e12a81d881b4b8c051e11f299203540d81d3e574dafe3a6`.
That deployment used backend image
`sha256:20b99cf0b20d271b465d8136538b8036a87e5a203a69fbef961bbb63998a164a`.
Candidate and deployed-container checks audited the live database read-only;
startup applied no migrations. Public probes verified edge/origin pages,
liveness, readiness, 308-question stats, pre-answer field secrecy,
post-submission feedback, redirects, security headers and cache policies. Only
the backend container was recreated; PostgreSQL and Nginx were not restarted,
and no environment variable or schema change was introduced.

The release-observability deployment has verified database backup
`pcep_db_pre_release_observability_20260927T175748Z.sql.gz` with SHA-256
`8b6e9ba96f9040a6449e79184c173797b50efe48e5a9ddf1653d8e07ffae58dd`
and rollback tag
`pcep-backend-rollback:20260927T175748Z-pre-release-observability`. Production
now runs backend image
`sha256:db9e94943104f6a50c3c0e797387b7a6ff91b94101233a77b19e6d5ae505921f`.
The frontend rollback root is
`.frontend.previous-20260927T175942Z-83644f8b`, with external backup
`frontend.20260927T175942Z-83644f8b`. Its entry chunk
`index-CzyLBNqR.js` has SHA-256
`9d877958fa6eceb869149f2c0694930eb1906e9cbcd04dfa3bb0cd09482158f5`;
both it and preceding `index-kkG5iDqv.js` returned 200 publicly after the atomic
swap. Only the backend container was recreated. PostgreSQL and Nginx were not
restarted, no migration ran and no required secret or environment setting was
added; the release values are embedded by the documented Make targets.

The controlled-PWA-update release has frontend rollback root
`.frontend.previous-20260927T180922Z-5a705a9c` and external backup
`frontend.20260927T180922Z-5a705a9c`. Its entry chunk `index-DnHg66tv.js` has
SHA-256 `b311a190a309ecc1aab620826d85c381c4767b3d6f8e634b9de0e151f63e7990`;
both it and preceding `index-CzyLBNqR.js` returned 200 publicly after the swap.
The public service worker matched the deployed file byte-for-byte and retained
`no-cache, no-store, must-revalidate`. This was a frontend-only atomic publish:
the healthy backend remains on release `0d92a2d8a4a0`, and PostgreSQL, Docker
services and Nginx were not restarted.

The cross-version-storage release has frontend rollback root
`.frontend.previous-20260927T181624Z-a5c6082b` and external backup
`frontend.20260927T181624Z-a5c6082b`. Its entry chunk `index-vuzCFG8p.js` has
SHA-256 `1a22857c17bfedc1de04878c1f84d98f526d345623fc6800a9a69da909727285`;
both it and preceding `index-DnHg66tv.js` returned 200 publicly after the swap.
This was another frontend-only atomic publish. The backend remained healthy on
release `0d92a2d8a4a0`; PostgreSQL, Docker services and Nginx were not restarted.

The active-exam ownership release has frontend rollback root
`.frontend.previous-20260927T183228Z-d731657c` and external backup
`frontend.20260927T183228Z-d731657c`. Its entry chunk `index-BNeBr8ht.js` has
SHA-256 `0a2d1489f7a6d13cba49edc370d2fef863b50534ca93a5a4ee6433fee85e8747`;
both it and preceding `index-vuzCFG8p.js` returned 200 publicly after the swap.
The public, live-root and validated-build service workers match at SHA-256
`60fd6ac7e1b0c36d5216f34a6b0b60cad0cb942bb10c5fbac67f63a81a552730`.
This was a frontend-only atomic publish. The backend remained healthy on release
`0d92a2d8a4a0`; PostgreSQL, Docker services and Nginx were not restarted, and
no migration or environment change was required. Privileged `nginx -t` passed.

The in-flight-grading release has frontend rollback root
`.frontend.previous-20260927T183928Z-5f82b196` and external backup
`frontend.20260927T183928Z-5f82b196`. Its entry chunk `index-DFDJJr0q.js` has
SHA-256 `1b4674ca20f95db6ef3d81eccf338a9ab88ce97629dc385077a5d8a1b4b7d68e`;
both it and preceding `index-BNeBr8ht.js` returned 200 publicly after the swap.
The live and validated-build service workers match at SHA-256
`15b726ff743866ed176d10b61d9b1a1a5ec4e039f22ffad8e1c2721e4b2194ca`.
The backend and PostgreSQL remained healthy, and neither was recreated. No
migration, environment change or Nginx reload was required.

The progress-synchronization release has frontend rollback root
`.frontend.previous-20260927T184840Z-90534d69` and external backup
`frontend.20260927T184840Z-90534d69`. Its entry chunk `index-DdurC_7K.js` has
SHA-256 `cc5c534ed657802ef988f1a4dce34b693b0182827e18a6b53d727cc530c88101`;
both it and preceding `index-DFDJJr0q.js` returned 200 publicly after the swap.
The public, live-root and validated-build service workers match at SHA-256
`54ce85b3d2edcd8159a54408eb5b62793cb9af8bae45dfaaba493a3169deba0d`.
Public liveness/readiness passed, both containers stayed healthy and privileged
`nginx -t` passed. No backend restart, database change, migration, environment
change or Nginx reload was required.

The supported-dependency release has frontend rollback root
`.frontend.previous-20260927T185919Z-038c21ed` and external backup
`frontend.20260927T185919Z-038c21ed`. Its entry chunk `index-BvxnNmgb.js` has
SHA-256 `13e44d0eaf16674031d9cc7bc151334a9087af62969e5a3117081faa6b1e2f9b`;
both it and preceding `index-DdurC_7K.js` returned 200 publicly after the swap.
The public, live-root and validated-build service workers match at SHA-256
`dc98c58d3433a575737a3a2887748b3e5601644512f03e4f86d689a71ec27701`.
The backend and PostgreSQL stayed healthy and privileged `nginx -t` passed. No
backend restart, database change, migration, environment change or Nginx reload
was required.

The supported Python dependency release runs backend revision
`3d00516c0af7` in image
`sha256:8f048f1a6a1acc2d0d55ee1cfe8aaa3d3e0498a275fe708aceec00d617d3c49c`.
The verified pre-deploy dump is
`pcep_db_20260928-020852.sql.gz` (SHA-256
`cbda97ed3a6185a50994e24247b8b5c9d38b409419357fe749ba077834b1a718`),
stored with mode `0600`. Because BuildKit had already replaced the local
candidate tag before the previous image was tagged, rollback release
`0d92a2d8a4a0` was rebuilt from that exact Git tree as
`pcep-backend-rollback:20260928-020834-release-0d92a2d8a4a0` and verified as a
non-root image. Startup found no migration to apply. Only the backend container
was recreated; PostgreSQL and Nginx were not restarted, no schema changed and no
new environment setting was introduced. The live database audit, public API
smoke tests and privileged `nginx -t` all passed after replacement.

The rollback-safe deployment command is host-side operational tooling and did
not require another container replacement, database change or Nginx reload.
Future routine backend releases should use `make deploy-backend`; the standalone
build target remains available for local and CI image validation.

The container-hardening release runs backend revision `9d8ad66c11dc` in image
`sha256:7a2c74dd5c5e4a0a5a0defe72692c3c0a46a4e12d50d0510a8ffebf32093439d`.
The exact preceding image is retained as
`pcep-backend-rollback:20260927T232725Z-release-3d00516c0af7`. The verified
mode-`0600` database dump is `pcep_db_20260927T232725Z.sql.gz` with SHA-256
`73b6f1b0ae12f6a462af66c7af193207ed8cf40cd5d5a63baffdfe969dc22fa1`.
The automated workflow confirmed the candidate revision and deploy settings,
found no pending migration, recreated only the backend, waited for readiness,
confirmed migration state, audited all 308 live questions and matched the public
release header. A separate public smoke test found no pre-answer fields and
normal post-answer feedback; the exact live image passed Trivy and contains no
test suite or development settings. PostgreSQL and Nginx were not restarted,
no schema or environment setting changed, and privileged `nginx -t` passed.

The CI action pinning changes only repository automation. It required no
production deployment, service restart, migration or environment change.

The Practice-recovery release has frontend rollback root
`.frontend.previous-20260927T235046Z-7ef8c998` and external backup
`frontend.20260927T235046Z-7ef8c998`. The published release is
`d21757e7d12e`; entry chunk `index-Br9GlvNG.js` has SHA-256
`e14654e9b84f6029d6c01557ecc5a56ca470430378018afb657faa633578ad77`, and
the public service worker matches the live root at SHA-256
`f78da35316c71215edec571540f8a64aa9ecdce21a299678db7a3dcaab59212c`.
The preceding `index-BvxnNmgb.js` remains public for open tabs. Fresh live
Chromium verified the release marker, answer-safe quiz payload, post-submit
Practice snapshot, reload/resume path and mobile fit. Public liveness, readiness,
post-submit feedback and cache policies passed; privileged `nginx -t` passed.
This was a frontend-only atomic publish. Backend and PostgreSQL stayed healthy,
and neither was recreated; no migration, environment change or Nginx reload was
required.

The explanation-quality release runs backend revision `8026db95920d` in image
`sha256:845f17b60f7e39805b5510eda51e7fec1a5e701ce5025eb1c09c8ad7c140c8d9`.
The exact preceding image is retained as
`pcep-backend-rollback:20260927T235520Z-release-9d8ad66c11dc`. The verified
mode-`0600` database dump is `pcep_db_20260927T235520Z.sql.gz` with SHA-256
`e8360da1d169294c730d54c8b9094ed01d6c67b5ffe426cce18950ce633082e5`.
Candidate and live-container checks found no migrations, and the read-only live
audit passed all 308 questions under the new explanation rules. Public release,
readiness, pre-answer secrecy and post-submit feedback probes passed; the deployed
image has zero fixable HIGH/CRITICAL Trivy findings. Only the backend was recreated.
PostgreSQL and Nginx were not restarted, no schema or environment setting changed,
and privileged `nginx -t` passed. The frontend remains on `d21757e7d12e`.

The Flashcard reliability release is published at frontend revision
`698aed939783`. Its rollback root is
`.frontend.previous-20260928T131219Z-c91e4306`, with the external copy
`frontend.20260928T131219Z-c91e4306`. The entry chunk `index-Dpng6iol.js` has
SHA-256 `c0ee07f0dfd2863d6c2e47964b4f9efec76592d8703b1503640f529c8a27712b`,
the Flashcard chunk `FlashcardView-DoabSnWm.js` has SHA-256
`d26f8f3a4175af41483c341397e1fe08b4bbf32fc7714b3987bbb928000a7095`,
and the public service worker matches the live file at SHA-256
`2a8c5fe666df0f9c90fa9da75d881f95158e365de655f5e93c4bf72f94810c2e`.
The previous entry chunk remains public for open tabs. Fresh live Chromium at
390 px verified the exact release, an answer-safe Flashcard set, valid post-reveal
feedback, zero horizontal overflow, zero axe violations and return to setup after
Quit. The only console message was the already tracked Cloudflare JavaScript
detection injection being blocked by CSP. Public liveness/readiness, security and
cache headers passed; privileged `nginx -t` passed. This was a frontend-only atomic
publish. Backend and PostgreSQL remained healthy, no service was recreated, and no
migration, environment change or Nginx reload was required.

The Search request-guard release is published at frontend revision
`afcb584383f8`. Its rollback root is
`.frontend.previous-20260928T132226Z-55b810ea`, with the external copy
`frontend.20260928T132226Z-55b810ea`. The entry chunk `index-DCCl6zcZ.js` has
SHA-256 `3b59332e86be9b0566e82429225cf8aebfd4f0a0f38a58ea6fb727d09a1b9701`,
and the public service worker matches the live file at SHA-256
`9d3b0f257538c0b0af731942140c1b198924ca6d7b5f9d33d078932d5085ed8d`.
The preceding entry chunk remains public and byte-identical for open tabs. Fresh
live Chromium issued two Search submissions in one render and observed exactly one
API request, then verified 20 answer-safe previews, an answer-safe selected drill,
zero horizontal overflow and zero axe violations at 390 px. The only console message
was the existing Cloudflare JavaScript detection injection blocked by CSP. Public
liveness/readiness and privileged `nginx -t` passed. This was a frontend-only atomic
publish; backend, PostgreSQL and Nginx were not restarted or reloaded, and no schema
or environment setting changed.

The Flashcard keyboard release is published at frontend revision
`555d4abb3e08`. Its rollback root is
`.frontend.previous-20260928T132755Z-0153c4b6`, with the external copy
`frontend.20260928T132755Z-0153c4b6`. The entry chunk `index-CIl0VRdG.js` has
SHA-256 `f325b9db94ca57f735c70d141c5b92a2d0b215bc000f0ef9540c9a2f41296603`,
the Flashcard chunk `FlashcardView-ZCoMqwZ-.js` has SHA-256
`7410c19f55b215a0f8fcfc911776024520dc3fa4e78e544bad1d5b4c951956fd`,
and the public service worker matches the live file at SHA-256
`e9cf494357fe1f6e611eaae6c1d4d98d952ab4f12f28125724243b8e738fe4a4`.
The preceding entry chunk remains public and byte-identical. Fresh live Chromium at
390 px verified the exact release, answer-safe deck, Space reveal, strict feedback,
focus transfer, `aria-keyshortcuts`, `2` self-rating and advancement to the second
card, with zero axe violations and no horizontal overflow. The existing Cloudflare
JavaScript detection injection blocked by CSP remained the only console message.
Public liveness/readiness and privileged `nginx -t` passed. This frontend-only atomic
publish recreated no service and required no schema, environment or Nginx change.

The Flashcard recovery release is published at frontend revision
`b5b4c4cd6d34`. Its rollback root is
`.frontend.previous-20260928T141732Z-009836b2`, with the external copy
`frontend.20260928T141732Z-009836b2`. The entry chunk `index-CaNGPjNn.js` has
SHA-256 `f0e354cc33cca99d6ced978b2f4d706648033654a93028e83b28aa19c5372372`,
the Flashcard chunk `FlashcardView-BgOPM-Y1.js` has SHA-256
`47d3707d38daa3db1faf95fcb6744ecb0c31a89944c3ca689c16f54f38fce3ba`,
and the public service worker matches the live root at SHA-256
`794b00bfcf265a19e87a91f4c531028cf2baa9f0f70715da938334741992aae8`.
The preceding entry chunk remains publicly available for open tabs. Fresh live
Chromium at 390 px verified the exact release, a 30-question answer-safe deck,
revealed-card snapshot, reload and resume without another answer request, advancement,
cleanup on Quit, zero axe violations and no horizontal overflow. The existing
Cloudflare JavaScript-detection injection blocked by CSP remained the only console
message. Public readiness reported the database up, stats reported 308 questions,
security/cache headers passed and privileged `nginx -t` passed. This frontend-only
atomic publish recreated no service and required no migration, environment or Nginx
change.

The scheduled-Flashcard release is published at frontend revision
`e2dc67e42cdf`. Its rollback root is
`.frontend.previous-20260928T142655Z-dea2e684`, with the external copy
`frontend.20260928T142655Z-dea2e684`. The entry chunk `index-CiGqy7Qe.js` has
SHA-256 `3e1f775a216219fc0309ffbd9ca0fa5b476898f2044bbb4170e1e0c581f3cf26`,
the Flashcard chunk `FlashcardView-BxGdMo08.js` has SHA-256
`e87fc3f9f252ffd923820cb8e200ea609956714cccea65509727af53fa3e2421`,
the Dashboard chunk `Dashboard-FoDP83kd.js` has SHA-256
`e49678ebb355ae9589459ca5c7589ad52374206bc7efc6a56698963e4af61c80`,
and the public service worker matches the live root at SHA-256
`bf3cc8bb9e381fe541db3c58ec65026151a590d6e31e901799ee2a8dc15517e6`.
The preceding entry chunk remains public. Fresh live Chromium at 390 px seeded four
valid local due records from an answer-safe production set, requested the exact four
IDs as Flashcards, found no answer metadata in the response or recovery snapshot,
resumed after reload and cleared the copy on Quit. Both active and recovery screens
had zero axe violations and no horizontal overflow. The existing Cloudflare
JavaScript-detection injection blocked by CSP remained the only console message.
Public liveness/readiness, the 308-question snapshot, asset retention and privileged
`nginx -t` passed. This frontend-only atomic publish recreated no service and required
no migration, environment or Nginx change.

The Admin question-quality release runs backend revision `5a6a74d844a7` in
image `sha256:a17df052f4203cb47ff505f26e96b691e7a975f93cc3013ce4187e8bd86138b3`.
The exact preceding image is retained as
`pcep-backend-rollback:20260928T143816Z-release-8026db95920d`. The verified
mode-`0600` database dump is `pcep_db_20260928T143816Z.sql.gz` with SHA-256
`9f1427a3cb789ac03f0b1e37f1f60334e9fad0e21b34a98761f477e522aa2c12`.
Candidate and live-container checks found no migrations, and the read-only live
audit passed all 308 questions. The deployed Admin applies the same snippet,
syllabus, explanation-quality and exact-duplicate gates as the audit command;
its answer preview was verified against live data with two queries for ten rows.
Public liveness, readiness, stats, pre-answer secrecy, post-submit feedback and
Admin login probes passed. The image has zero fixable HIGH/CRITICAL Trivy
findings, and privileged `nginx -t` passed. Only the backend was recreated;
PostgreSQL and Nginx were not restarted, and no schema or environment setting
changed. The frontend remains on `e2dc67e42cdf`.

The saved-list Flashcard release is published at frontend revision
`ba418410e9ab`. Its rollback root is
`.frontend.previous-20260928T181456Z-8f25cad1`, with the external copy
`frontend.20260928T181456Z-8f25cad1`. The entry chunk
`index-BHgfBIlK.js` has SHA-256
`59ea8eae67d97e13edf7fc2cfb8b3735b3e3de4639796f14c8ecf1ead36bcb3b`,
the Flashcard chunk `FlashcardView-D0CSQAd1.js` has SHA-256
`dc875c3ee5ecf8591395aee9d45afde0e0dcb856f97918d4b5b6269934d49af6`,
the Dashboard chunk `Dashboard-7M7QyFKq.js` has SHA-256
`4b7d834fb5231553e0778df36b8f09d9844e04db1147f490e661e8aa31d055c2`,
and the public service worker matches the live root at SHA-256
`7b8cfa20d9676adcd0b55761e713518e209a7f5d2c642d7c3db04b32608af0d5`.
The preceding entry chunk remains public. Fresh live Chromium at 390 px used
separate production questions for the bookmark and mistake Flashcard paths,
verified the exact ID requests, found no answer metadata in either public payload
or recovery snapshot, and confirmed cleanup on Quit. Both decks had zero axe
violations and no horizontal overflow. The existing Cloudflare JavaScript-detection
injection blocked by CSP remained the only console message. Public liveness,
readiness, the 308-question snapshot, security/cache headers and privileged
`nginx -t` passed. This frontend-only atomic publish recreated no service and
required no migration, environment or Nginx change.

The Search Flashcard release is published at frontend revision
`bb77e0d3ec0a`. Its rollback root is
`.frontend.previous-20260928T182601Z-fed676ad`, with the external copy
`frontend.20260928T182601Z-fed676ad`. The entry chunk `index-OCiJNGCE.js`
has SHA-256
`0efcb71dfa7a732298e49f67dd8a0c2a03ff452c3bf8ad8a0a8c09fa67300acf`,
the Flashcard chunk `FlashcardView-ngBszpfV.js` has SHA-256
`cbe25e5c13a9b9a345b5c167d396404b37d55e65fd2e4baab47620964f468c8c`,
and the public service worker matches the live root at SHA-256
`6168464cea2ad157ebdbed6b08c7e5f5211f26ff6a2e710b20469f0357420cb3`.
The preceding entry chunk remains public. Fresh live Chromium at 390 px selected
production Search results 152 and 185, observed those exact IDs in the public
quiz-set request, found no answer metadata in the Search payload, deck payload or
recovery snapshot, and verified reload, resume and cleanup on Quit. The active
deck had zero axe violations and no horizontal overflow. The existing Cloudflare
JavaScript-detection injection blocked by CSP remained the only console message.
Public liveness, readiness, the 308-question snapshot, cache headers and
privileged `nginx -t` passed. This frontend-only atomic publish recreated no
service and required no migration, environment or Nginx change.

The adaptive-Flashcard release is published at frontend revision
`e4568e267944`. Its rollback root is
`.frontend.previous-20260928T211617Z-b16004f3`, with the external copy
`frontend.20260928T211617Z-b16004f3`. The entry chunk `index-CeGUX6L7.js`
has SHA-256
`c8c1e5eadf6be85e16c0f6c440ce3a9cfba518a0bc20109b875eb0877b4b3a14`,
the Flashcard chunk `FlashcardView-B7VawKjo.js` has SHA-256
`750f9199f4116ed6131ce1e636102188a3b3c6b69c74b0dc18a7ec28f92ea408`,
the Dashboard chunk `Dashboard-HBLVwTZz.js` has SHA-256
`7b3a7efd74b0a59f146e5b5ee76e8ce089459c3ea879c89eb4b61991be3521bb`,
and the public service worker matches the live root at SHA-256
`53de5029353f939863c3f69cee892e3215780bcaaf50e10695be3c198029e34d`.
The preceding entry chunk remains public. Fresh live Chromium at 390 px seeded
production IDs 254, 320, 258 and 232 from an answer-safe public set; the adaptive
ranking requested 232, 254, 258 and 320 in both Flashcards and Practice. Neither
response nor the unrevealed recovery snapshot contained answer metadata. Reload,
explicit resume and cleanup on Quit passed, and the setup, active deck and recovery
screen had zero axe violations and no horizontal overflow. The existing Cloudflare
JavaScript-detection injection blocked by CSP remained the only console message.
Public liveness, readiness, the 308-question snapshot, HTTPS redirect, TLS, security
and cache headers, retained assets, Compose validation and privileged `nginx -t`
passed. This frontend-only atomic publish recreated no service and required no
migration, environment or Nginx change.

The targeted-order release runs backend revision `7207b1bc2fb9` in image
`sha256:fe9c54a960d1a39658a0205a7441d64c5e68bbd23ab753a80d6a637548914cb1`.
The exact preceding image is retained as
`pcep-backend-rollback:20260928T212443Z-release-5a6a74d844a7`. The verified
mode-`0600` database dump is `pcep_db_20260928T212443Z.sql.gz` with SHA-256
`79a34f220a16c9e38e9f603debeece5861a776d8cade5d52035200ede8a63a42`.
Candidate and live checks found no migration to apply, and the read-only audit
passed all 308 questions. A public ID request for 232, 254, 258 and 320 with
`count=3` returned 232, 254 and 258 in that order without answer metadata;
post-submit feedback remained available. Fresh live Chromium then generated an
adaptive plan ordered 317, 272, 391 and 251 and found the same order in the API
response and answer-safe Flashcard recovery snapshot. The deployed image runs as
the non-root user with a read-only filesystem and has zero fixable HIGH/CRITICAL
Trivy findings. Liveness, readiness, stats, Compose validation and privileged
`nginx -t` passed. Only the backend was recreated; PostgreSQL and Nginx were not
restarted, and no schema or environment setting changed. The frontend remains on
`e4568e267944`.

The analytics build marker has no runtime deployment requirement because Vite
removes it from `dist/index.html`; the verified output still loads the same
`/u/script.js` with the existing privacy attributes. The external-volume
declaration resolves to the three existing `pcep_webapp_*` volumes and live
container mountpoints. No volume, container or data was recreated for that
configuration change. Fresh installations must create the named volumes once,
as documented in README and the operations runbook.

The production-smoke stage requires no migration, image rebuild, service restart,
Nginx reload or environment change. Its local command already validates the live
domain. The scheduled GitHub workflow and expanded contract become active when
the monitoring commits are pushed to the repository's default branch.

The focused-review/safe-quit frontend release is published at revision
`c9e084aeb6d0`. Its rollback root is
`.frontend.previous-20260928T215206Z-09288549`, with external copy
`frontend.20260928T215206Z-09288549`. The entry chunk
`index-BJQLTMCQ.js` has SHA-256
`7b69edf3d30ddf3bbb0e23d0866041aad6a661f808837f19690cf0acaff44bba`,
the Review chunk `ReviewScreen-PScnr1uT.js` has SHA-256
`6e90aad983b9fedf3182edb89b3171faa5d88c3599c447cfb9dd57c6f83915a3`,
the Flashcard chunk `FlashcardView-D6XNoa5e.js` has SHA-256
`f13e267ddc273f7fbce2ea90813e297d3cce2611fbc1101b08cd858731ee94ab`,
and `sw.js` has SHA-256
`51812da1303de83673f8368addc0799bca00bb4ba25481083b0f0f12d5f0216c`.
The preceding entry chunk remains publicly available with immutable caching.
Fresh live Chromium at 390 px completed ten production questions, built a focused
Flashcard queue for production question 226 and observed that exact ID in the
request, public response and answer-safe recovery snapshot. Cancelling Quit kept
the active deck and recovery; confirming it returned to setup and cleared the
snapshot. The report and active deck had zero axe violations, no horizontal
overflow and no unexpected console errors. Public release, shell assets,
liveness, readiness, the 308-question snapshot, answer secrecy, ordered drills,
HTTPS redirect, dependency audits, Django deploy checks, Compose validation and
privileged `nginx -t` passed. This frontend-only atomic publish recreated no
service and required no migration, environment, Nginx or Cloudflare change; the
backend remains on `7207b1bc2fb9`.

The complete-targeted-list frontend release is published at revision
`5bb231373a9e`. Its rollback root is
`.frontend.previous-20260929T000906Z-36df0112`, with external copy
`frontend.20260929T000906Z-36df0112`. The entry chunk
`index-CucivH6J.js` has SHA-256
`36152ba055bb3fdd67c4b000eb9efd2ca71235d76b3b9d965f72de77078a5657`,
the stylesheet `index-BiaZTj8j.css` has SHA-256
`3e8f0c0cbed485b50c4243657c08a0465381b7b07a706372de8ae519c8b26c0c`,
and `sw.js` has SHA-256
`d6cd4b9ef74667d2b97340fe211568d7d41b84be29c03b4c801994f588029ee4`.
The preceding entry chunk remains public with immutable caching. Fresh live Chromium
at 390 px seeded 100 answer-safe production bookmarks and observed all 100 IDs in
the same order in the request, public response and Practice recovery snapshot.
No answer metadata entered any payload or recovery record; the active session had
zero axe violations and no horizontal overflow, and confirmed Quit cleared recovery.
All 279 Vitest tests, lint, formatting, the production build, all 29 Playwright flows,
the complete public smoke, healthy Compose services and privileged `nginx -t` passed.
This frontend-only atomic publish recreated no service and required no migration,
environment, Nginx or Cloudflare change; the backend remains on `7207b1bc2fb9`.

The quick-session frontend release is published at revision `394106bdd184`. Its
rollback root is `.frontend.previous-20260929T002821Z-0a318f94`, with external
copy `frontend.20260929T002821Z-0a318f94`. The entry chunk
`index-DF72O0dT.js` has SHA-256
`b4db4adf4230023a84cc34eb18e5f67d74f171a4c7e520d7bd1ee7440986ce06`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`ef1f1128f258c770e05d1cf77baa34a920c97905c1f255024f41d8a313a0018b`.
The preceding entry chunk remains public with immutable caching. Fresh live Chromium
at 360 px verified all five size controls at 49×44 px, then requested five hard
objective-3.1 questions from module 3. The public response and answer-safe Practice
recovery each contained exactly five questions; the active session had zero axe
violations and no horizontal overflow, and confirmed Quit cleared recovery. The
complete public smoke, healthy Compose services and privileged `nginx -t` passed.
This frontend-only atomic publish recreated no service and required no migration,
environment, Nginx or Cloudflare change; the backend remains on `7207b1bc2fb9`.

The stable-session-preference frontend release is published at revision
`a4d088d59f68`. Its rollback root is
`.frontend.previous-20260929T003822Z-7171d3a4`, with external copy
`frontend.20260929T003822Z-7171d3a4`. The entry chunk `index-Dp8gSLJn.js`
has SHA-256
`a3daa51b9466b6087fa84ce3dbe5fd898ea5ee91c55b5a92f023a89b98699ddf`,
and `sw.js` has SHA-256
`8735f7d2050476db16dc1eb58dfd672423e1a8dab1c2123fdb750f3cc48044f1`.
The preceding entry chunk remains public with immutable caching. Fresh live Chromium
at 390 px selected a real two-question module-3/objective-3.2/hard scope while the
preferred size was 30. It observed `count=30` in the request, two answer-safe public
questions, a two-question recovery snapshot and the stored preference still at 30;
after confirmed Quit, setup restored the 30-question control. Axe reported zero
violations and the page had no horizontal overflow. The complete public smoke,
healthy Compose services and privileged `nginx -t` passed. This frontend-only atomic
publish recreated no service and required no migration, environment, Nginx or
Cloudflare change; the backend remains on `7207b1bc2fb9`.

The legacy-session-size-migration frontend release is published at revision
`5ebac4c24946`. Its rollback root is
`.frontend.previous-20260929T005732Z-f7a29d2d`, with external copy
`frontend.20260929T005732Z-f7a29d2d`. The entry chunk `index-Ck3w9S7S.js`
has SHA-256
`509d8370714c6f95e18602e79ffe527c70f58d06365cc850a8d86df17e9d2c38`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`2847ea8dc69cc0fadac639f88d0c72321508d9c14c7880b8a7df5724a044ace4`.
Fresh live Chromium at 360 px started with a version-1 setup preference containing
the formerly persisted count 1. Setup displayed and selected 30 without rewriting
that record; explicit Start then requested and received 30 public questions, saved
the supported preference and created a 30-question answer-safe recovery snapshot.
Neither payload contained answer metadata or explanations. Axe reported zero
violations, the active page had no horizontal overflow, no page error occurred and
confirmed Quit cleared recovery. The only console error was the already tracked CSP
rejection of Cloudflare's injected inline script. The complete public smoke, healthy
Compose services and privileged `nginx -t` passed. This frontend-only atomic publish
recreated no service and required no migration, environment, Nginx or Cloudflare
change; the backend remains on `7207b1bc2fb9`.

The strict-feedback-validation frontend release is published at revision
`6347f257013c`. Its rollback root is
`.frontend.previous-20260929T010701Z-dce05b0a`, with external copy
`frontend.20260929T010701Z-dce05b0a`. The entry chunk `index-DMN60Fwh.js`
has SHA-256
`85f7e85da06e88e532e0d913b4108d2dfac6d8c5b1819368cf912e937555b883`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`36c60543c3cef56fda72fd50c359855453163c7dd207405a4fb423da881d6690`.
Fresh live Chromium at 390 px exercised all three study modes against production.
Practice accepted exactly the four canonical feedback fields, stored that same shape,
remained axe-clean and had no horizontal overflow. Flashcards accepted the same API
contract and retained only the correct choice ID and explanation after Reveal. A
five-question Exam returned exact question/choice-bound results with consistent
correctness and cleared recovery after grading. Every initial question response and
recovery question list remained answer-safe, and no page error occurred. The complete
public smoke, healthy Compose services and privileged `nginx -t` passed. This
frontend-only atomic publish recreated no service and required no migration,
environment, Nginx or Cloudflare change; the backend remains on `7207b1bc2fb9`.

The search-result-invalidation frontend release is published at revision
`b9cc1f4e7ce5`. Its rollback root is
`.frontend.previous-20260929T134000Z-69753513`, with external copy
`frontend.20260929T134000Z-69753513`. The entry chunk `index-BnfnBZPS.js`
has SHA-256
`0e7f1a17e26ae6658d33e82712a413b6169bcc561bf36c12717d750861e0f04c`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`7abffe73c5f2f68f3195acd3b58052182640764dc7bcbcf4bbff65f58e883443`.
Fresh live Chromium at 390 px loaded 20 answer-safe `output` results, selected one,
then changed the query to `list` and observed the old results and selection disappear
before submission. The refreshed query returned seven answer-safe previews. Selecting
the first two launched IDs 264 and 269 in the same order through the request, public
response and Flashcard recovery, with no answer metadata. The active deck had zero
axe violations, no horizontal overflow and no page error; confirmed Quit cleared its
recovery. The complete public smoke, healthy Compose services and privileged
`nginx -t` passed. This frontend-only atomic publish recreated no service and required
no migration, environment, Nginx or Cloudflare change; the backend remains on
`7207b1bc2fb9`.

The recoverable-quiz-loading frontend release is published at revision
`895bc228f00a`. Its rollback root is
`.frontend.previous-20261003T194740Z-21fbb148`, with external copy
`frontend.20261003T194740Z-21fbb148`. The entry chunk `index-Dfq68GhQ.js`
has SHA-256
`787b6182ada5dd27c892ef5d5ea82ecaa0c51e1435682c4193fda42890a69998`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`723bd15ee8d493e67c7d363290d8d32732b3172bc2ef40163c03d6f37cb6ee28`.
Fresh live Chromium at 390 px replaced only its first question request with a
synthetic 503. The error screen was axe-clean and offered Retry; that action sent
the same `count=5`, `module3`, `medium` parameters to the real production API,
which returned five answer-safe questions. Settings retained the requested size,
active recovery used the validated five-question result, and neither public data nor
recovery exposed answer metadata. The active screen was also axe-clean and fit the
viewport, with no page errors; confirmed Quit cleared recovery. The browser recorded
only the known CSP rejection of Cloudflare's injected inline script plus the deliberate
503 resource message. The complete public smoke, healthy Compose services and
privileged `nginx -t` passed. This frontend-only atomic publish recreated no service
and required no migration, environment, Nginx or Cloudflare change; the backend
remains on `7207b1bc2fb9`.

The accurate-exam-review frontend release is published at revision
`1b4414fffe8f`. Its rollback root is
`.frontend.previous-20261003T195545Z-583f3e53`, with external copy
`frontend.20261003T195545Z-583f3e53`. The entry chunk `index-XRzmLEw1.js`
has SHA-256
`7f1d8179b384f0de3a7f52c22101d520828cdbd73d2646f75b7b4adfa8c4ed1a`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`724b684a24bfb7b2fca640f64fe557f5dceeef40d42926693cb3562ec80d2932`.
Fresh live Chromium at 390 px completed a real five-question Exam by selecting
the first public choice for each question. The grading request exactly matched
those five local selections and returned three correct plus two wrong results.
Opening the full review showed three correct outcomes, two wrong outcomes and the
two corresponding `your pick` labels, with zero questions marked skipped. The
pre-submit question payload and persisted progress remained answer-safe, completed
grading cleared active recovery, axe reported zero violations, the page fit the
viewport and no page error occurred. The only console error was the already tracked
CSP rejection of Cloudflare's injected inline script. The complete public smoke,
healthy Compose services and privileged `nginx -t` passed. This frontend-only
atomic publish recreated no service and required no migration, environment, Nginx
or Cloudflare change; the backend remains on `7207b1bc2fb9`.

The bounded-frontend-assets release is published at revision `217ead04cbb9`.
Its rollback root is `.frontend.previous-20261003T200342Z-609df6e6`, with
external copy `frontend.20261003T200342Z-609df6e6`. The entry chunk
`index-1PWEO9Xo.js` has SHA-256
`7c30932fbb48266390f05a56f7fde818c9a0868d67949d1461ac735a6d7d57d4`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`e2e5bf6bc11aaf2e4c2fc7638448ad001bdd5a159358fa7b78bf901075f7e9da`.
The live asset directory decreased from 318 files to 202; both the rollback root
and external backup retain all 318 prior files. The preceding entry chunk and its
lazy Review chunk return 200, while a deliberately checked expired chunk returns 404. Fresh live Chromium at 390 px loaded the new entry, Dashboard and Exam lazy
chunks with 200 responses. The active Exam was axe-clean, fit the viewport, raised
no page error and cleared recovery after confirmed Quit. The only console error was
the already tracked CSP rejection of Cloudflare's injected inline script. The
complete public smoke, healthy Compose services and privileged `nginx -t` passed.
This atomic publish recreated no service and required no migration, environment,
Nginx or Cloudflare change; the backend remains on `7207b1bc2fb9`.

The cancellable-quiz-loading frontend release is published at revision
`661f6052ffd7`. Its rollback root is
`.frontend.previous-20261004T002626Z-8fa6f6d7`, with external copy
`frontend.20261004T002626Z-8fa6f6d7`. The entry chunk `index-CyBUF6ZU.js`
has SHA-256
`54b762eb7a946364741bd77b93ed14ac05dae047df17b9b53932ada953b07ca3`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`9ee2460f26636c0cf6aa3e1c7947cb4cc5737234c935112ed678f8684871c121`.
Fresh live Chromium at 390 px fetched a real answer-safe five-question response,
held it for five seconds only in the browser and cancelled loading in about 192 ms.
The delayed response was then delivered but could not leave setup or create Exam,
Practice or Flashcard recovery. The exact requested preferences remained saved.
The loading screen was axe-clean, fit the viewport and raised no page error; the
only console error was the already tracked CSP rejection of Cloudflare's injected
inline script. The complete public smoke, healthy Compose services and privileged
`nginx -t` passed. Live asset retention remained bounded at 202 files in the new
root and both complete rollback copies. This frontend-only atomic publish recreated
no service and required no migration, environment, Nginx or Cloudflare change; the
backend remains on `7207b1bc2fb9`.

The access-log and runtime-security backend release is deployed at revision
`0ae831c94921`, image
`sha256:cbc7750c37d37378008f5cb8929517a639fdaa60a50cb2f6425baa6d4a6f1abe`.
Its immediate rollback tag is
`pcep-backend-rollback:20261004T004020Z-release-a9b5c67de6ba`. The private
mode-0600 database backup is `pcep_db_20261004T004020Z.sql.gz`, with SHA-256
`2b04d5ed4a562530fcd96fe1195da9a128b3e8205548f61d4128eb644da04b50`.
The deployed image contains the patched PCRE and OpenSSL `u3` packages and passes
the blocking Trivy scan with zero fixable HIGH/CRITICAL OS or Python findings.
The public smoke verified the matching release, all 308 questions, answer-safe
payloads and exact targeted order. A live public request that copied the internal
health marker was logged exactly once using Nginx's generated request ID, while
successful Compose probes produced zero access-log entries across two intervals.
Compose remained healthy and privileged `nginx -t` passed. No migration,
environment, Nginx or Cloudflare change was required; PostgreSQL was not restarted.

The scan-gated backend release is deployed at revision `2915c622166b`, image
`sha256:1fd6b76b4bd499b0c7578992b332e0a536f8b517180c530443eae3a81d4bf005`.
Its immediate rollback tag is
`pcep-backend-rollback:20261004T005001Z-release-0ae831c94921`. The private
database backup is `pcep_db_20261004T005001Z.sql.gz`, with SHA-256
`684e5861bc2cbc05b4425ed30e3ab3efe7298ece5de6cba33aa1b86c46f516b3`.
The live deployment proved the new boundary end to end: Trivy scanned that exact
immutable candidate ID with zero fixable HIGH/CRITICAL findings, and only after
the scan succeeded did Compose recreate the backend. Post-start Django checks,
the read-only 308-question audit, the complete public smoke, healthy Compose
services and privileged `nginx -t` passed with no backend error. No migration,
environment, Nginx or Cloudflare change was required; PostgreSQL was not restarted.

The strict-quiz-set-validation frontend release is published at revision
`443dcb89dc6c`. Its rollback root is
`.frontend.previous-20261004T005558Z-338697e7`, with external copy
`frontend.20261004T005558Z-338697e7`. The entry chunk `index-CE5D4ae1.js`
has SHA-256
`7628fc17f30275a2f7f7768c5a5d0dea99c9a46a51c4706c05f926b15012daf3`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`0925cdb2a75c8fff3989c37ca7668e41737959493194b5d32fe1c67a4b78e19c`.
Fresh live Chromium at 390 px fetched a real answer-safe five-question response
and changed only its count to six inside the browser. The app rejected it without
creating Practice, Exam or Flashcard recovery; Retry fetched five current questions,
started Practice and persisted the exact validated public order without answer
metadata. Confirmed Quit cleared recovery. Both states had zero axe violations,
no horizontal overflow and no page error; the only console error was the tracked
Cloudflare inline-script CSP rejection. All 299 Vitest tests, lint, formatting, the
production build and all 31 Playwright flows passed. The complete public smoke,
healthy Compose services and privileged `nginx -t` also passed. This frontend-only
atomic publish recreated no service and required no migration, environment, Nginx
or Cloudflare change; the backend remains on `2915c622166b`.

The race-safe progress-import and heading-order frontend release is published at
revision `abb4876cda89`. Its rollback root is
`.frontend.previous-20261004T121417Z-7e80707e`, with external copy
`frontend.20261004T121417Z-7e80707e`. The entry chunk `index-CjNaA0xh.js`
has SHA-256
`4cea429d7146b38c09ebdb9b044ac0cd91e04f2cc4a5df67c548e6b97f83a8ea`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`0ef25abf17d600fc830cb70de39a627b112c49c65dfd7a8627b3259d9fad3372`.
The live root matches the validated build byte for byte. Fresh Chromium at 390 px
delayed the first of two backup reads past the second: only the second preview
remained, the busy status cleared, the section heading was level two, axe reported
zero violations, the page fit the viewport and no page error occurred. The only
console error was the tracked CSP rejection of Cloudflare's injected inline script.
All 300 Vitest tests, lint, formatting, the production build and all 31 Playwright
flows pass. The complete public smoke, healthy Compose services and privileged
`nginx -t` also pass. This frontend-only atomic publish recreated no service and
required no migration, environment, Nginx or Cloudflare change; the backend remains
on `2915c622166b`.

The Axios-remediation frontend release is published at revision `6a2b681be5ec`.
Its rollback root is `.frontend.previous-20261004T122546Z-aff485fe`, with external
copy `frontend.20261004T122546Z-aff485fe`. The entry chunk
`index-De_Qtudf.js` has SHA-256
`2feeece66764f24ab4ec3cfc2f81f0bb9f30c65e0b9a3aff9ab05cb0d113cf2c`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`dc43de0e0ca2654e940384287a57cf8b7677bd5d9e3709157b1761867f6d4550`.
The live root matches the validated build byte for byte. Fresh Chromium at 390 px
used the real API through Axios 1.20.0 to fetch 30 questions and submit one Practice
answer; both requests returned 200. The pre-submit response contained no correctness
flag, answer ID or explanation, while feedback appeared after submission. Axe found
zero violations, confirmed Quit cleared recovery, the page fit the viewport and no
page error occurred. The only console error was the tracked CSP rejection of
Cloudflare's injected inline script. `npm audit` reports zero vulnerabilities; all
300 Vitest tests, lint, formatting, the production build and all 31 Playwright flows
pass. The complete public smoke, healthy Compose services and privileged `nginx -t`
also pass. This frontend-only atomic publish recreated no service and required no
migration, environment, Nginx or Cloudflare change; the backend remains on
`2915c622166b`.

The frontend-identity release is published at revision `4c1342bcf849`. Its
rollback root is `.frontend.previous-20261004T123652Z-77f6c005`, with external
copy `frontend.20261004T123652Z-77f6c005`. The entry chunk
`index-CIv-eH4e.js` has SHA-256
`d49b460dd9336955dffac693401c9a041dfc49272c5e3414d1748f938be8f9ed`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`3a4c78272add0eb126d6ae0dd377fd976b3051323baac8cfba1bac77c825753b`.
The live root matches the validated build byte for byte. Before publication, the
new smoke correctly rejected the old shell for its missing marker. After the atomic
swap it passed with `frontend_release=4c1342bcf849` and
`backend_release=2915c622166b`, and the public HTML exposed exactly one marker.
Fresh Chromium at 390 px confirmed that marker matches the React footer, axe found
zero violations, the page fit the viewport and no page error occurred. Compose
remained healthy and privileged `nginx -t` passed. This frontend-only publication
recreated no service and required no migration, environment, Nginx or Cloudflare
change.

The live Cloudflare Tunnel now matches `pcep.micutu.com` through an explicit rule
before the shared catch-all. It sends the fixed PCEP Host/SNI to
`https://127.0.0.1:443` and sets `noTLSVerify: false`; OpenSSL independently
verified the local ECDSA certificate and TLS 1.3 connection. The old root-owned
mode-0600 configuration is backed up at
`/home/micu/backups/pcep/cloudflared.config.20261004T123936Z.yml`, SHA-256
`7eb66fa5fc473b829add66d28e069bc85ff3b569ed3f7800dba1e043499e72ff`.
Both the candidate and installed configs passed `cloudflared ingress validate`,
PCEP selected the explicit rule, the separate `preturi` rule remained unchanged,
and unknown hosts still selected the catch-all. Restarting only cloudflared changed
its PID from 3947471 to 1588150; one probe returned 530 during the roughly one-second
reconnection window, after which all four QUIC connections registered and the
connector readiness endpoint reported healthy. The complete PCEP public smoke
passed, representative PCEP, special-route and catch-all domains returned 200,
Compose stayed healthy and privileged `nginx -t` passed. Nginx, Docker and
PostgreSQL were not restarted; no migration, application deployment or Cloudflare
dashboard change was required.

The recoverable-completion frontend release is published at revision
`406410646a21`. Its rollback root is
`.frontend.previous-20261004T130206Z-3ecff7ea`, with external copy
`frontend.20261004T130206Z-3ecff7ea`. The entry chunk
`index-CWZ5Tsya.js` has SHA-256
`ff476c84cd6286de0a2d8218809816347b084f592ccd4df37b9b27ea87f75fce`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`fdcbea864a5aea9cf09e7722d08043b627e45121f21b85b2b237d3d75ab9ede2`.
The live root matches the validated build byte for byte. Fresh Chromium at 390 px
completed five real Practice answers, then synthetically rejected only the final
`pcep.progress` write. The last question and `pcep.activePractice` recovery remained
available with the explicit retry action; after restoring writes, the retry created
exactly one history record, cleared recovery and opened the report. Axe found zero
violations, the page fit the viewport and no page error occurred. The only console
error was the tracked CSP rejection of Cloudflare's injected inline script. All 302
Vitest tests, lint, formatting, the production build and all 31 Playwright flows
pass. The complete public smoke reports the new frontend and existing backend
revisions, Compose remains healthy, cloudflared reports four ready connections and
privileged `nginx -t` passes. This frontend-only atomic publication recreated no
service and required no migration, environment, Nginx or Cloudflare change; the
backend remains on `2915c622166b`.

The storage-warning recovery patch is published at revision `a4823b8b2cf5`.
Its rollback root is `.frontend.previous-20261004T130641Z-06ee2876`, with
external copy `frontend.20261004T130641Z-06ee2876`. The entry chunk
`index-DNkG6cO9.js` has SHA-256
`2ba8937b503dd5d32b23c1b725b31ddac784ba106a726d69a3330994d9c471b2`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`774e5432e5405d90a18a86c2833e10395102f81578dfb23124e8c86bc5daba00`.
The live root again matches the validated build byte for byte. A fresh 390 px
Chromium session forced the final progress write to fail, observed the warning and
intact Practice recovery, restored storage, retried completion and then observed one
history record, cleared recovery and zero remaining persistence warnings. Axe found
zero violations, the page fit the viewport and no page error occurred; the tracked
Cloudflare inline-script CSP rejection remained the only console error. All 303
Vitest tests, lint, formatting and the production build pass, along with the focused
browser recovery flow. Public smoke reports the new frontend revision, Compose is
healthy, cloudflared has four ready connections and privileged `nginx -t` passes.
No service was recreated and no migration, environment, Nginx or Cloudflare change
was required; the backend remains on `2915c622166b`.

The API error-header change is installed from commit `1992145`. The previous
root-owned vhost is backed up as
`/home/micu/backups/pcep/nginx.pcep.20261004T130929Z.conf`, mode 0600, with SHA-256
`dea53d7b38ff450585c2db7dd5fe175ac70f7ae0e26259c4f10f2dde610f5b4b`.
Both named 413/429 locations in the loaded `nginx -T` output contain the restrictive
API CSP. A public 413 response confirmed that CSP, all common headers, no-store JSON
and request ID end to end. The complete public smoke passed, Compose remained healthy,
cloudflared retained four ready connections and the Nginx journal recorded a clean
graceful reload. No container or tunnel was restarted; no migration, application
artifact, environment or Cloudflare setting changed. Rollback consists of restoring
the backup over `/etc/nginx/sites-available/pcep.micutu.com`, running `sudo nginx -t`
and gracefully reloading Nginx.

The key-scoped storage-recovery frontend release is published at revision
`6b4ddc8aa65f`. Its rollback root is
`.frontend.previous-20261004T133250Z-d64e2e3b`, with external copy
`frontend.20261004T133250Z-d64e2e3b`. The entry chunk
`index-CAxXwSPT.js` has SHA-256
`e4e971fba12b369fbf587b197f99c456e92e7afbd17ab5e561f6005d1ee51401`,
the stylesheet `index-joTgEVXq.css` has SHA-256
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`c88bc571311e403c5575cffc999c24cc82f6fff59bf4ccdd741e995bb8927a5e`.
The public files match the validated build byte for byte. Fresh Chromium at 390 px
forced only the final `pcep.progress` write to fail, then successfully persisted a
theme change. The progress warning remained visible after that unrelated write and
cleared only when the progress retry succeeded; the active Practice recovery remained
until then, exactly one history record was created, and the report opened normally.
Axe found zero violations, the page fit the viewport and no page error occurred. The
tracked Cloudflare inline-script CSP rejection remained the only console error. All
303 Vitest tests, lint, formatting, the production build and the focused Playwright
storage flow pass. Public smoke reports this frontend revision and backend
`2915c622166b`; Compose is healthy, cloudflared has four ready connections and
privileged `nginx -t` passes. No service was recreated and no migration, environment,
Nginx or Cloudflare change was required.

The isolated Nginx CI check now covers the failure mode found during the live CSP
review. Beyond syntax, it starts the digest-pinned Nginx image with disposable TLS
material on a random loopback port and asserts the generated 413 and 429 status,
exact JSON, no-store policy, restrictive CSP and request ID, plus `Retry-After` for
throttling. `bash -n`, ShellCheck and the complete isolated runtime check pass. Its
cleanup removed the temporary container, and the check made no request to or change
in production. This test-only stage required no deployment, migration, environment,
Nginx, Docker Compose, tunnel or Cloudflare change.

The answer-key constraint release runs backend revision `32d3b643f71e`, image
`sha256:9a25ef1eb9be5d4f979df5b7850796482729071b4a03d5fce1dcb5cab6b396d2`.
Before replacement, the deploy retained rollback image
`pcep-backend-rollback:20261004T200008Z-release-2915c622166b` and created the
mode-0600 database backup
`/home/micu/backups/pcep/pcep_db_20261004T200008Z.sql.gz`, SHA-256
`23ab288e657159562520b990c3014f0f7c2a519b9af790db19f182a5fbc897e9`.
The reviewed migration plan contained only `0011`; after rollout, PostgreSQL reports
the unique partial index `one_correct_choice_per_question` on `question_id` with
predicate `WHERE is_correct`; every migration is applied and no operation remains.
Both the standard SQLite and isolated PostgreSQL 16 suites pass all 216 backend
tests. Source and live audits
pass all 308 questions, Django checks pass, and the immutable candidate has zero
fixable HIGH/CRITICAL Trivy findings. Public smoke passes with
`backend_release=32d3b643f71e`, `frontend_release=6b4ddc8aa65f`, answer-safe payloads
and targeted ordering. The backend and database are healthy, cloudflared is active
and privileged `nginx -t` passes. The deploy recreated only the backend and applied
the compatible additive migration; it did not restart PostgreSQL, reload Nginx,
publish a frontend, reseed questions or change environment/Cloudflare settings.
Rolling the backend image back is compatible with the retained constraint; remove
the constraint only through the reviewed reverse migration if that becomes necessary.

The Pyodide truncation-reporting frontend is published at revision
`b16a9c49ef93`. Its rollback root is
`.frontend.previous-20261004T200615Z-518df7be`, with external copy
`frontend.20261004T200615Z-518df7be`. The entry chunk
`index-DmmfjSFL.js` has SHA-256
`bbd52a9934b5692b479f224039b8174447e83bc853b2542c93ae6227e557fb11`,
the lazy runner chunk `CodeRunner-C7Zdp7L1.js` has SHA-256
`4c497da67591b004462b6bda623e4d1b96d7366351915d96a36fed73a545a1a2`,
the stylesheet remains
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`5b43c8e0b5a05d9136edaaf1bfeee02782d0f876e00f56d59a84a4df778d7e30`.
The public files match the validated build byte for byte. All 303 Vitest tests,
lint, formatting and the production build pass; the real-runtime Playwright flow
also passes syntax/runtime errors, bounded output, timeout and worker recovery.
Fresh live Chromium at 390 px loaded the published release and self-hosted Pyodide,
ran 20,000 characters of output, observed the explicit 10,000-character warning,
fit the viewport, found zero axe violations and raised no page error. The tracked
Cloudflare inline-script CSP rejection remained the only console error. Public smoke
passes with this frontend and backend `32d3b643f71e`; Compose is healthy,
cloudflared is active and privileged `nginx -t` passes. This atomic frontend
publication recreated no service and required no migration, environment, Nginx or
Cloudflare change.

The retry-safe session-completion frontend is published at revision
`1f3bf87dc97a`. Its rollback root is
`.frontend.previous-20261004T202246Z-c9285ba2`, with external copy
`frontend.20261004T202246Z-c9285ba2`. The entry chunk
`index-DbsD99DC.js` has SHA-256
`99437ba7b34c91cf8b12bf309b3571ae681bb8efe2b73388a5d2e3755dbb65fb`,
the stylesheet remains
`a10b33a1b90f5b97a54cc51e4753d0fa8dec9fcf7c0ea304fcfc7d508d7f9f9c`,
and `sw.js` has SHA-256
`462c1c2d42b1f43d1d698edb82842784fefc09516c52208f6564abe02e5de492`.
All 20 files in the published release match the validated build byte for byte.
All 305 Vitest tests, lint, formatting, the production build and the 22 quiz
Playwright flows pass. Fresh live Chromium at 390 px forced only removal of the
completed Practice recovery record to fail after the progress snapshot was written.
The retry action preserved one history entry and one study attempt per question,
then removed recovery and opened the report; the attempt and recovery IDs matched.
The page fit the viewport, axe found zero violations, and no page or unexpected
console error occurred. Public smoke passes with this frontend and backend
`32d3b643f71e`; Compose is healthy, cloudflared is active and privileged `nginx -t`
passes. This atomic frontend publication recreated no service and required no
migration, environment, Nginx or Cloudflare change.

The initial PostgreSQL hardening was deployed from commit `c917fa6` as image
`sha256:286dc161b78dcd0ccc5e9d5e62bb07a3e17bb47674294a99b898e437dd4571b2`,
built from the reviewed PostgreSQL 16.15 Alpine digest. The prior image is retained
as `pcep-postgres-rollback:20261004T203125Z-pre-hardening`. The verified pre-change
logical dump is `/home/micu/backups/pcep/pcep_db_20261004T203125Z.sql.gz`, mode
0600, SHA-256
`a261517fef6ea7bbf4baf53c06a54c8d03da6a5e7e44aa3989cf6e4e59162f7d`.
It restored under the exact hardened runtime with 308 questions, 1,232 choices and
29 migrations, then retained those counts across restart. The disposable runtime
test independently verified initialization, writes, restart persistence, a read-only
root, zero capabilities and `no-new-privileges`; Trivy reports zero fixable
HIGH/CRITICAL findings after removal of the unused vulnerable `gosu` binary.

Only `pcep_db` was recreated for the image/runtime change; it became healthy in
seven seconds and retained the external PGDATA volume. The database credential was
then rotated, the `.env` was replaced atomically and only `pcep_backend` was
recreated to load it. The protected environment rollback copy is
`/home/micu/backups/pcep/pcep.env.pre-password-rotation-20261004T203916Z`.
An isolated TCP authentication probe confirms the previous credential is rejected.
Both containers are healthy, the live database audit is clean, public smoke passes
with backend `32d3b643f71e` and frontend `1f3bf87dc97a`, cloudflared is active and
privileged `nginx -t` passes. No schema migration, volume replacement, Nginx reload
or Cloudflare change was required.

The least-privilege role follow-up is deployed from commit `26b72ae` as database
image `sha256:665b0e8864d3399e8fb10828cc869c3065682262e289b56dacbfda8c8374b0e9`.
The mode-0600 pre-change application dump is
`/home/micu/backups/pcep/pcep_db_20261004T204938Z.sql.gz`, SHA-256
`e19604b1fb14b560b96ee2e106c8bbc9cd32fbc5dd2d8788ff4d7c207a42a0a0`.
The separate mode-0600 global-role dump is
`/home/micu/backups/pcep/pcep_globals_20261004T204938Z.sql.gz`, SHA-256
`e7b3810ef8c16319d2e24c2df9b5730f61dcae3ec1e51b39c13b5d55737dee4d`.
The latter captures the rollback state that a normal per-database dump omits.

The migration was first exercised on a restored copy, including application DDL,
forbidden role creation and restart. Live, the bootstrap owner became `pcep_admin`;
the recreated `pcep_user` has no superuser, create-role, create-database, replication
or row-security-bypass privilege. It owns `pcep_db` plus its public tables and
sequences, while the administrator retains system schemas and `plpgsql`. Django's
migration check and question audit pass under the restricted role. `.env.db` is a
separate ignored mode-0600 file; TCP authentication works for both roles, and an
environment-key audit proves the administrator credential is absent from the backend
container. Only `pcep_db` was recreated, becoming healthy in seven seconds without
changing its external volume. Both containers and the tunnel are healthy, public
smoke passes, and privileged `nginx -t` passes. No data/schema migration, frontend or
backend publication, Nginx reload or Cloudflare change was required.

Final validation after the completion, container and database-role stages is clean:

- `python -m pytest -q` from `backend/`: 216 passed.
- Source and live database question audits: 308 questions, no warnings.
- `make django-check`: no production deployment warnings.
- `npm run test`: 305 passed; lint, Prettier and the production build pass.
- `npm run e2e`: all 31 Chromium flows pass, including both accessibility themes,
  recovery, answer secrecy, PWA behavior and the real Pyodide runtime.
- `make audit`: both Python requirement sets and npm report no known vulnerability.
- Backend and PostgreSQL blocking Trivy scans: zero fixable HIGH/CRITICAL findings.
- Hardened PostgreSQL runtime, isolated Nginx error contracts, Compose rendering,
  privileged live `nginx -t` and the complete public production smoke all pass.

### Dependency reproducibility and rollback recovery — 2026-10-05

Python production and development dependency graphs are now committed as complete
SHA-256 lock files. Local/CI installs require hashes and binary distributions; the
backend image verifies the production lock while collecting wheels and again during
its network-free runtime install. `pip-tools` 7.6.1 and `make lock-backend` provide
the reviewed regeneration path. Scheduled dependency auditing installs the hashed
development environment instead of resolving the scanner's transitive dependencies
dynamically.

The frontend builder now pins Node 24.21.0 on Alpine 3.24 by official
multi-architecture digest
`sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1`.
Its Compose wrapper maps the invoking host UID/GID while retaining a disposable
home/cache, so the non-root builder can safely replace `frontend/dist` on hosts
whose operator is not UID 1000. CI now builds and runs this exact builder, and all
four primary CI jobs have explicit time bounds.

A pre-deploy test build exposed the existing safety rule that the exact live image
must be snapshotted before its local tag is displaced. The first deployment attempt
therefore stopped before backup, build or service replacement. Recovery deliberately
did not use `docker commit`, which could preserve runtime secrets in image metadata.
The deployment tool now accepts an explicit fallback only when exact live image
metadata is unavailable. It requires non-root `appuser`, matching release metadata,
no embedded application/database secret keys, a clean `pip check` in a networkless,
read-only, capability-free container, and a clean blocking image scan before tagging
the fallback. Normal deployments still require the exact running image.

The retained `2915c622166b` rollback was independently scanned and exercised
read-only against the live schema (`migrate --check` and the 308-question database
audit) before use. Release `ab91beebe4f2` is now live as backend image
`sha256:503dd4c69ed5aab723fe00bc275dc0f55905209dfe77e3b71fb352ddb6958903`.
Its fallback rollback tag is
`pcep-backend-rollback:20261005T081403Z-release-2915c622166b`. The verified mode-0600
database backup is `/home/micu/backups/pcep/pcep_db_20261005T081403Z.sql.gz`,
SHA-256 `148df20780dd0b67adf9d91678f3bf8dfe58b32abd9171a93b5132610089d894`.

Validation for this follow-up is clean:

- fresh hash-only development install plus `pip check`;
- 218 backend tests and 305 frontend tests;
- lint, Prettier and both host/container production frontend builds;
- all 31 Playwright flows;
- Python/npm advisories: zero;
- candidate and fallback fixable HIGH/CRITICAL findings: zero;
- Django deploy check, migration check and 308-question live audit: clean;
- Compose healthy, privileged `nginx -t` and complete public smoke: clean.

Commits `a60c21f` and `ab91bee` contain the implementation. Only the backend was
recreated. PostgreSQL, its volume, the frontend publication, Nginx and Cloudflare
were not changed; no migration or seed operation ran. The public frontend remains
`1f3bf87dc97a`.

### npm install-script and registry-integrity controls — 2026-10-05

Normal frontend installs use the exact Node 24.21.0/npm 11.19.0 toolchain in CI and
the digest-pinned builder. A follow-up removed reliance on npm 11.18+'s
`strict-allow-scripts`, which older npm versions merely warn about and ignore.
Every supported install now starts with `npm ci --ignore-scripts`, validates the
exact lifecycle-script inventory in both the lockfile and installed package
metadata, and requires every artifact to have an official-registry URL plus SHA-512
integrity. It then rebuilds and exercises only `esbuild@0.25.12`. The optional
`fsevents@2.3.3` installer remains blocked. The manifest retains the matching
allow/deny declarations as defense in depth for npm versions that support them,
without making enforcement depend on that support. Any new version, lifecycle
command or package with an install script fails before its code can execute.

The scheduled audit also validates the same inventory after its script-free install.
Both CI audit paths continue to verify registry signatures and provenance
attestations with `npm audit signatures`.

A clean no-cache builder install reports no packages with unreviewed install
scripts. The pinned tree verified registry signatures for all 518 dependency
packages and verified 169 provenance attestations; the vulnerability audit reports
zero findings. This is a build and CI control only: it does not alter the application
bundle or the running production services, database, Nginx or Cloudflare
configuration.

### Deprecated Workbox glob removal — 2026-10-05

The remaining npm install warning came from `workbox-build@7.4.1` constraining
`glob@^11.0.1`. The resolved `glob@11.1.0` already contains the published CLI
injection fix, so the warning did not represent an open `npm audit` vulnerability.
However, the entire 11.x line is deprecated. `vite-plugin-pwa@2.0.0` retains the
same Workbox dependency and therefore would not remove the warning.

The frontend now gives Workbox an exact scoped `glob@13.0.6` override. Workbox calls
only `globSync`, which remains available through glob 13's CommonJS export; the new
major removes the CLI and five no-longer-needed transitive packages. The override is
intentionally not ranged and must be removed once Workbox supports the current major
itself. A clean install has no glob deprecation warning, all 518 packages have
verified registry signatures, 169 have verified provenance attestations and the
vulnerability audit is clean. All 305 Vitest tests, lint, formatting, the production
PWA build with its 13-entry precache and all 31 Playwright flows pass, including the
offline-shell contract. No production or external repository state was changed.

### GitHub Actions runner and interpreter pinning — 2026-10-05

All push, pull-request, scheduled-audit and production-smoke jobs now select the
explicit Ubuntu 24.04 runner rather than the moving `ubuntu-latest` alias. This
prevents GitHub's announced October/November 2026 Ubuntu 26.04 migration from
changing the CI operating system without review. Python jobs also select exact
3.12.14, matching the digest-pinned backend image and the local validation
environment; the GitHub Actions Python manifest provides 3.12.14 builds for both
Ubuntu 22.04 and 24.04 on x64 and arm64.

The current `ubuntu-latest` label still resolves to Ubuntu 24.04, so this is an
environment freeze rather than an effective runner downgrade or application
change. It requires no production deployment or service restart. A later Ubuntu
26.04 move should be explicit and follow a complete CI run on that runner.

Local validation parsed all workflow YAML, rendered the Compose configuration and
ran all 218 backend tests under Python 3.12.14. The 308-question audit, both hashed
Python dependency audits, Django's production deploy check and the public production
smoke also pass. The hosted workflow will exercise the explicit runner on the next
push; no push was performed as part of this review.

### Daily database backup and restore validation — 2026-10-05

Pre-deploy dumps no longer provide the only database recovery points. A dedicated
host-side job now creates an atomic, mode-0600 `pg_dump` every day, writes and fsyncs
a SHA-256 sidecar, re-verifies every complete retained pair and keeps 30 daily
backups. It uses a non-blocking lock to reject concurrent runs. Retention happens
only after a new dump and checksum succeed, and its exact daily filename pattern
cannot select deployment dumps, role/configuration backups or release snapshots.
Corrupt, non-private or symlinked matching files fail closed; unpaired files remain
for operator review instead of being deleted.

The systemd oneshot runs as `micu` with no capabilities or production credential
file. Its host filesystem is read-only except for
`/home/micu/backups/pcep/daily`, and it reaches the database only through the Docker
Unix socket. The persistent timer runs at 01:17 local time with a randomized delay.
Unit validation covers successful retention, dump failure before retention,
unpaired-file preservation, matching-symlink refusal, checksum corruption and
bounded keep values.

The complete backend suite now passes all 227 tests under Python 3.12.14. Both
hashed dependency audits report no known vulnerability, the 308-question audit and
Django production check are clean, the systemd units verify, and Compose renders.

A real dump of the live database was created in a temporary mode-0700 directory,
then restored with `psql -X`, `ON_ERROR_STOP` and one transaction into a disposable,
network-isolated PostgreSQL 16.15 container running with the production security
controls. The restore produced 308 questions, 1,232 choices and all 29 migrations;
the partial unique index was present and `pcep_user` owned the question table. The
temporary dump and container were removed afterward. The remaining disaster-
recovery limitation is off-host durability: scheduled copies still reside on the
same physical server until an independently controlled destination is configured.

The hardened timer is enabled and waiting for its next run in the daily
01:17-01:32 local-time window. Two manual service executions completed successfully;
the latest mode-0600 backup is
`/home/micu/backups/pcep/daily/pcep_db_daily_20261005T133023Z.sql.gz`, SHA-256
`2b80f9e589adc8e930e3c9912a552a294ef5d944b03d9030dedb314505fc8d45`.
Both retained sidecars pass `sha256sum --check`. The final systemd security
analysis reports exposure 2.2/10 after network, device, namespace, process and
write-path isolation. No application or database service was restarted.

The separate frontend-retention dry run identified 55 old rollback roots and 55
matching backup copies beyond the newest five, representing 2.2 GiB of unique
allocated space across both locations. Nothing was removed: the filesystem still
has 140 GiB free, so cleanup remains an explicit operator-reviewed action rather
than part of the database-backup rollout.

### Tracked-file and Git-history secret scanning — 2026-10-05

The CI ops job now scans the current contents of every Git-tracked path and a text
rendering of all reachable commit history with the existing digest-pinned Trivy
0.75.0 secret detector. It fetches full history and fails rather than silently
accepting a shallow clone. The staging tree excludes every ignored or untracked
file, so production `.env` files, the operator's rclone credentials, local backups
and `.claude/` never enter the scanner container. The container has no network,
capabilities or writable root. Its working directory is fixed to `/`, outside the
read-only target at `/workspace`, so repository-controlled Trivy, ignore or secret
configuration is scanned as data but cannot configure the scanner.

The complete tracked tree and history scan reports no secret finding. A separate
temporary canary containing a synthetic GitHub token produced a redacted CRITICAL
finding and exit status 1, proving that the blocking path is active; that canary was
committed only in a disposable test repository, never entered this repository, and
was removed with the temporary scan tree. This control does not inspect intentionally
ignored runtime secrets and does not replace credential rotation if a real value
ever reaches Git history.

### Automated isolated restore drill — 2026-10-05

The newest complete daily database backup is now restored automatically every
Sunday at 03:17 local time, with up to 30 minutes of randomized delay. The drill
re-verifies all retained complete backup pairs, selects the newest, and obtains the
exact immutable image ID from the live PostgreSQL container without reading its
environment or connecting to its database. It starts a disposable PostgreSQL
container with no network, capabilities, writable root or persistent data volume;
all database storage is a bounded tmpfs. The source dump and checksum are mounted
nowhere and remain read-only to the host-side process.

The restore uses `psql` with `ON_ERROR_STOP` and one transaction, then verifies
positive question, choice and migration counts, `pcep_user` ownership, the valid
one-correct-choice partial index, exactly four choices and exactly one correct
choice for every question. It verifies the source checksum again after the drill
and removes the disposable container on success or any handled failure. A fixed
disposable container name also makes concurrent executions fail closed.

Unit coverage brings the backend suite to 237 passing tests. Both the direct drill
and the installed hardened systemd service restored 308 questions, 1,232 choices
and all 29 migrations from
`pcep_db_daily_20261005T133023Z.sql.gz` using PostgreSQL image ID
`sha256:665b0e8864d3399e8fb10828cc869c3065682262e289b56dacbfda8c8374b0e9`.
The timer is enabled for its next randomized run on 2026-10-11, the service reports
systemd exposure 2.2/10, and no disposable container remains. Production Compose
services stayed healthy and the complete public smoke passed without a restart.
This validates recoverability but does not resolve the separate same-host/off-host
durability limitation.

### Fail-closed encrypted offsite preparation — 2026-10-05

Off-host replication now has an implementation, tests, a hardened systemd service,
an inactive post-backup trigger and a CISO/incident runbook. The command accepts only
an rclone `crypt` remote at a dedicated non-root path with explicit standard
filename encryption, directory-name encryption, a password and distinct second
salt. It verifies every complete local backup pair, rejects stale scheduled input,
uploads only the newest dump and checksum with immutable `copyto`, downloads both
through the encrypted remote and verifies SHA-256 before reporting success. It has
no remote delete, purge, sync or retention path. The service consumes a minimal
PCEP-only rclone config through systemd encrypted credentials, keeps its runtime copy
on tmpfs and writes an atomic success marker only after round-trip verification.

The live blast-radius inventory currently reports zero Django users, zero database
sessions, 308 questions and 1,232 choices. The runbook nevertheless treats future
account identifiers, password hashes and sessions as in scope. Its CISO verdict is
to block activation until the provider, region/DPA, versioning or object lock,
dedicated least-privilege credential, separately stored crypt recovery material and
an independently tested failure/missed-success alert are documented. Journal-only
failure reporting does not satisfy that alert gate.

Read-only preflight correctly rejects both existing choices: `gdrive-vps-crypt` is
encrypted but inherits rclone's retiring shared Google OAuth client, while `r2` is a
raw S3 backend without a PCEP crypt wrapper. No backup was uploaded, no remote object
was changed, and the offsite systemd service/post-backup trigger were not installed.
Unit tests cover path/config fail-closed behavior, stale backups, safe command
selection, atomic success status, successful round-trip verification and simulated
remote corruption. The complete backend suite passes all 262 tests.

### Continuous systemd unit validation — 2026-10-05

Push/pull-request CI now resolves and validates all five repository-owned systemd
services/timers plus the offsite `OnSuccess` drop-in on Ubuntu 24.04. The validator
rejects symlinks, unexpected tree entries, unsafe filenames and drop-ins without a
repository-owned base unit before invoking `systemd-analyze verify` through an
explicit unit search path. This turns host-version directive compatibility and
drop-in composition into a blocking check rather than a manual deployment step.

The exact local command reports five valid units and one valid drop-in. Bash syntax,
workflow YAML, Compose rendering, the complete 262-test backend suite, tracked-secret
scan and public production smoke are clean. This CI-only control made no production
or systemd change; the encrypted offsite service and trigger remain uninstalled.

### Semantic GitHub Actions validation — 2026-10-05

Push/pull-request CI now runs the same `make check-workflows` entry point available
to operators. It downloads only the fixed Linux/amd64 actionlint 1.7.12 artifact,
verifies its exact SHA-256 before extracting the binary and validates all three
workflow files. ShellCheck integration remains mandatory for embedded shell blocks.

The validator passes workflow paths explicitly and supplies a trusted empty config,
so a repository-owned actionlint ignore rule cannot suppress its own finding. It
also rejects symlinks, nested content and unsafe names in `.github/workflows` rather
than silently omitting them. The current three workflows pass with no findings.
This is a CI-only control; it made no production, systemd or offsite-backup change.

### GitHub Actions security audit — 2026-10-05

The workflow check now adds `zizmor` 1.30.1's pedantic security analysis after
actionlint. Its Linux/amd64 archive is fixed by version and exact release SHA-256;
the binary runs explicitly offline, receives no GitHub token, loads no repository
configuration and honors no inline ignores. All workflow paths are supplied
explicitly and strict collection turns any parse/schema omission into a failure.

All three workflows pass with zero findings, including full action hash pinning and
matching version comments, minimal permissions, safe triggers, credential handling
and expression use. The local Bash/ShellCheck and semantic actionlint validations
also remain clean. This control changes only repository CI and documentation: no
push, deployment, service restart or production mutation was performed.

### Reviewed dependency update proposals — 2026-10-05

Dependabot configuration now covers the two ecosystems whose updates the existing
CI can reproduce directly: hash-pinned GitHub Actions and the frontend npm manifest
plus lockfile. Checks run weekly on separate mornings in Europe/Bucharest. Routine
versions wait seven days after release, minor/patch changes are grouped and major
changes remain isolated. The three-PR limit controls routine noise but does not
delay security update PRs when that repository feature is enabled; no update is
auto-merged. Dependabot alerts/security updates remain an explicit GitHub repository
setting and must be confirmed there after the configuration reaches the default
branch.

Python and container updates remain manual by design. Python changes require both
hashed lock files to be regenerated and audited together, while base-image changes
require coordinated tag/digest review, rebuild, runtime checks and image scans.
The daily dependency advisory workflow continues to cover idle periods. Strict
offline zizmor validation now includes `.github/dependabot.yml` as an explicit
input, so invalid or unsafe automation configuration blocks push/pull-request CI.
This repository-only change performs no external update, push or production action.

### Pull-request dependency-diff preparation and graph activation — 2026-10-05

A separate workflow is prepared to review the dependency delta for pull requests
targeting `main`. Its check fails for newly introduced or upgraded dependencies
with known vulnerabilities rated moderate, high or critical across runtime,
development and unknown scopes. Once activated and made required, this closes the
gap between audits of the resolved tree and the exact dependency change proposed by
a PR.

The official dependency review action is pinned to the full commit for `v5.0.0` and
runs on the explicit Ubuntu 24.04 image with a five-minute bound. The workflow has
only `contents: read`, persists no checkout credential, posts no PR comment and has
no write-capable token permission. OpenSSF score output is disabled because it is
informational. License enforcement is also explicitly disabled until the project
has a reviewed legal allowlist rather than an implicit scanner policy.

Local actionlint and strict offline zizmor validation cover the workflow syntax,
immutable action pin, permissions and untrusted-PR trigger. The dependency comparison
itself requires GitHub's hosted dependency graph. The graph and Dependabot alerts
were enabled through GitHub's documented repository endpoint. A subsequent HTTP 204
status, the public dependency page and an authenticated dependency comparison all
confirm availability. GitHub generated an SBOM with 609 packages and 1,150
relationships; the initial open-alert list is empty. Dependabot security updates
remain disabled, so this activation cannot open automated remediation PRs.

`main` still has no branch protection and the repository has no ruleset. Therefore
the local workflow is not yet an effective merge control: the change must be pushed,
a hosted pull-request run confirmed and its check then marked required. No repository
push, production deployment or service restart was performed; the only external
mutation was enabling the dependency graph and Dependabot alerts.

### Hosted CI portability corrections — 2026-10-06

The first GitHub-hosted execution exposed three environment-dependent assumptions
that local validation did not reproduce. One offsite-backup test requested mode
`0770` through `mkdir` but did not account for the runner's `0022` umask removing
group write; the test now applies the intentionally unsafe mode explicitly before
asserting its rejection. The systemd validator also resolved production's absolute
Python path against the runner filesystem. It now stages the exact units and
drop-ins in an isolated temporary root with non-executed fixtures for the expected
host dependencies, and treats every `systemd-analyze` diagnostic as a failure.

The browser run found an ambiguous text locator because the temporary merge SHA
itself contained `4d`, matching a two-statistic assertion, plus a race where a
multi-tab recovery test read local storage before React persisted the session. The
locator now requires exact text and the ownership test polls the observable storage
contract instead of assuming synchronous persistence. The exact failing merge SHA
was reproduced locally: all 31 Playwright flows passed without a retry, and the
multi-tab case passed ten consecutive repetitions. The complete 262-test backend
suite, ShellCheck, isolated systemd validation, actionlint and pedantic offline
zizmor also pass. These corrections change tests and CI validation only; they do not
alter the application bundle, production services or backup activation state.

The subsequent `main` run exposed one more browser-only timing condition. Axe
sampled both quiz workspace tabs during their color transition immediately after
the progress view opened. The serialized trace showed transient contrast ratios
of 1.72:1 and 4.44:1 even though both settled light-theme states meet the required
ratio. Playwright now emulates the reduced-motion user preference for every E2E
flow, exercising the application's existing reduced-motion stylesheet and letting
accessibility scans inspect settled colors deterministically. Reduced motion also
limits animations to one iteration. The contrast rule remains enabled; no Axe
finding is suppressed or excluded.

### Enforced `main` merge controls — 2026-10-06

GitHub branch protection now applies to `main`, including repository administrators.
Every change must use a pull request whose head is current with `main`; conversations
must be resolved and the resulting history must remain linear. Force pushes and
branch deletion are disabled. The approval count is deliberately zero because the
repository has one maintainer, avoiding a rule that could never be satisfied while
still preventing direct pushes.

The four CI jobs plus `Reject newly vulnerable dependencies` are required and bound
to GitHub Actions app ID 15368, so a different integration cannot satisfy a gate by
reusing its display name. GitGuardian remains advisory because the repository-owned
Ops job already performs a blocking tracked-file and Git-history secret scan; an
external service outage therefore cannot prevent an emergency maintenance PR. The
protection API returned the exact configured checks, strict update requirement,
administrator enforcement, pull-request requirement, linear-history requirement,
conversation-resolution requirement and disabled force-push/deletion settings.
This setting change did not deploy code, restart a service or alter production data.

### Immediate transitive npm advisory response — 2026-10-06

The first `main` run after branch-protection documentation detected a newly reported
HIGH-severity event-loop denial-of-service advisory in the development-only
`source-map-js@1.2.1` resolution. The package is transitive through the existing
PostCSS, Tailwind and jsdom toolchain; no application manifest requested it directly.
The preceding pull-request audit had passed, so the later push failure demonstrates
that registry-backed audits fail closed when advisory data changes between runs.

The lockfile alone now resolves the already-compatible parent ranges to patched
`source-map-js@1.2.2`, updating its tarball URL and verified integrity value without
adding a direct dependency or changing any other resolution. npm reports zero
vulnerabilities; all 518 installed packages have verified registry signatures and
169 have verified provenance attestations. Lint, formatting, the production build,
all 305 Vitest tests and all 31 Playwright flows pass. This remediation changes no
production service, database, environment or deployment state.

### Frontend test and build toolchain modernization — 2026-10-06

The independent `@testing-library/jest-dom` 7 and Vitest 5 Dependabot updates were
reviewed against their Node and assertion-contract breaking changes, merged, and
confirmed by a fully green `main` run. The standalone Vite 8 update could not even
install because `@vitejs/plugin-react` 4 does not declare a Vite 8 peer range. The
build upgrade therefore moves Vite 6.4.3 to exact 8.3.1 together with the smallest
compatible plugin release, `@vitejs/plugin-react` 5.2.0. The config's local PWA
import now includes its `.js` extension, removing Vite's native-config-loader
compatibility warning.

The seven-day dependency cooldown is preserved across the resolved graph. Vite
8.3.3 and plugin-react 6.1.2 were published inside that window and were not selected.
Vite's Rolldown range is explicitly held at 1.2.11 because a fresh npm resolution
otherwise selected 1.2.12 before it completed the same cooldown. Vite 8 replaces
esbuild with Rolldown, so the graph no longer needs any lifecycle installer. The
script-free installer and inventory checker now execute no dependency code at all;
optional macOS-only `fsevents@2.3.3` remains explicitly blocked.

The final locked graph reports zero npm vulnerabilities, 514 verified registry
signatures and 170 verified provenance attestations. Lint, Prettier, all 305 Vitest
tests, the PWA production build and all 31 Playwright flows pass on the host. The
digest-pinned Node 24.21.0/Alpine builder also installs the graph from scratch and
produces the PWA successfully. This is a source and build-tooling change only; no
production service was deployed or restarted and no production data was touched.

### Exact-main CI recovery trigger — 2026-10-06

The coordinated Vite 8 pull request passed dependency review and every required CI
job. GitHub then created no push-triggered CI run for the rebased `main` commit,
although the later scheduled production smoke succeeded on that exact SHA. The CI
workflow now also accepts a manual dispatch, allowing an operator to run the same
four bounded jobs against current `main` when event delivery is absent. PR and push
triggers, required-check names, permissions and branch protection remain unchanged.
This recovery control neither contacts production nor changes deployment state.

### Offsite activation preflight hardening — 2026-10-06

The activation audit confirmed that the PCEP offsite service and backup-success
drop-in remain uninstalled, with no PCEP environment file or encrypted systemd
credential present. The operator's existing shared rclone configuration contains a
Google Drive crypt remote that is not PCEP-dedicated and a raw R2 backend; neither
meets the activation gates and neither was reused. No upload or remote mutation was
performed. The latest private local dump was instead restored successfully in the
network-isolated disposable PostgreSQL container, reproducing 308 questions, 1,232
choices and 29 migrations.

The fail-closed preflight now applies its bounded safe-segment grammar to the backend
path wrapped by the crypt remote as well as to the requested destination. Absolute
paths, trailing or repeated separators, traversal, unsafe backend names and a crypt
remote that wraps itself are rejected before backend feature checks or any transfer.
Forty-four focused tests cover the offsite control. Independent credentials,
provider versioning/object lock, an offline recovery key, a tested alert and vendor
review are still absent, so the CISO verdict remains **BLOCK activation**.

### Cloudflare R2 offsite candidate profile — 2026-10-07

Official provider and local rclone documentation were reviewed without using or
revealing the operator's existing credentials. A new Cloudflare R2 bucket is a
technically eligible destination only when created in the EU jurisdiction, kept
private, accessed with an Object Read & Write token scoped to that bucket, wrapped by
the dedicated rclone crypt remote and protected by a native R2 Bucket Lock on the
physical `encrypted/` prefix for at least 30 days. R2 does not expose standard S3
versioning or S3 Object Lock; the provider-native lock must be recorded accurately.

Cloudflare account audit logs cover configuration actions but not object access.
Data Access Logs are best-effort, omit failed requests and are generally unavailable
for jurisdictional buckets, so they cannot satisfy the independent detection gate.
The runbook now includes the exact secret-free configuration shape and evidence
requirements. No bucket, token, lock, upload, credential, systemd unit or production
service was changed. DPA/subprocessor review, offline key custody, independent alert
testing and an incident tabletop remain open; the verdict remains **BLOCK
activation**.

### Cloudflare R2 profile enforcement — 2026-10-07

The offsite preflight now binds execution to the reviewed `cloudflare-r2-eu` profile
instead of accepting an arbitrary encrypted backend. The redacted configuration must
contain exactly the crypt wrapper and its backend. It rejects a non-Cloudflare
provider, a non-EU or malformed endpoint, non-auto region, ambient credentials,
session tokens, enabled bucket-creation checks, missing static credentials, extra
backend/crypt options and any physical path other than
`bucket-name/encrypted`. Forty-four focused tests pass.

This is deliberately not presented as provider attestation: the local file cannot
prove Cloudflare token scope, actual bucket jurisdiction, private-access state or the
Bucket Lock rule. Those activation gates still require independently reviewed
control-plane evidence. No remote API mutation, upload, secret, systemd installation
or production restart occurred; the CISO verdict remains **BLOCK activation**.

### Production verification credential exposure — 2026-10-08

At approximately 16:52 UTC, a post-deployment verification command rendered the
backend container's complete environment into the private operator transcript. This
exposed the Django signing key and the `pcep_user` application-database password.
The database administrator credential was not present in the backend environment
and was not exposed. Detection was immediate, and the transcript was treated as an
untrusted disclosure channel rather than relying on later deletion.

The affected database role has no superuser, database-creation, role-creation,
replication, row-security-bypass or object-ownership capability; its table grants
remain limited to application DML. Production contained zero Django users and zero
Django sessions at containment time, and the learner API has no authentication
surface. This bounds the known credential scope but does not prove that the rendered
values were never observed outside the host.

Both exposed values were rotated. The backend was stopped while the application
role password and the two mode-0600 environment files were updated, then only the
backend was recreated from the already-scanned release image. The first revocation
probe incorrectly used PostgreSQL loopback, which is covered by a local `trust`
rule; that attempt rolled back automatically. The completed rotation used a
disposable client on the Compose network, matching the backend's SCRAM-authenticated
TCP path. It proved that the replacement credential succeeds and the disclosed
credential is rejected. At 16:54:17 UTC the backend was healthy with synchronized
replacement values, and public smoke testing passed for release `e17371c6d416` with
308 questions, the admin route disabled and the browser runner isolated. Repository
and reachable-history scanning plus GitHub secret, dependency and code-scanning
alerts remained clean.

Future environment verification must parse inspection JSON and assert selected
properties without printing the environment array, values, hashes or other
secret-derived material.

### Backend persistent write-surface removal — 2026-10-11

The production API had a read-only root filesystem but still mounted persistent
static and media volumes as writable. The API has no upload surface, production
does not install or route Django admin, and system Nginx serves separate host
directories rather than either Docker volume. Read-only inspection found 318
generated static files and no media files, so the mounts provided no live feature.
In a backend compromise they could instead preserve attacker content or consume
unbounded host storage across container replacement.

The backend no longer runs `collectstatic` at startup and receives no persistent
filesystem mount; only its size-bounded, `noexec,nosuid,nodev` `/tmp` tmpfs remains
writable. Previously created volumes and their contents are not deleted, preserving
rollback evidence and avoiding a destructive migration. Deployment now parses
container inspection JSON internally and fails unless the exact candidate image,
unprivileged user, read-only root, dropped capabilities, no-new-privileges setting,
process/memory limits, hardened tmpfs, loopback-only port, restart policy and zero
persistent mounts all match the reviewed contract. It emits only boolean posture,
never environment values.

The dominant STRIDE risks were denial of service through disk exhaustion and
tampering/persistence after an application compromise. No new vendor, credential,
personal-data flow or regulatory scope is introduced. The incident runbook exists;
the human tabletop remains outstanding, and no FAIR loss estimate is asserted
without business-impact inputs. Because the legacy volumes remain recoverable and
the prior image is retained by deployment, the CISO verdict is **SHIP** after the
normal backup, candidate scan, CI and production smoke gates pass.

### Learner-origin third-party script removal — 2026-10-11

The learner CSP allowed Cloudflare's browser-insight script and telemetry endpoint.
Cloudflare also injected the beacon into the public HTML, so this was an active
third-party execution path rather than an unused allowlist. The application already
uses Umami through same-origin `/u/` routes, making that extra supplier trust
unnecessary.

The policy now restricts both `script-src` and `connect-src` to the learner origin.
Edge-injected inline code and third-party script delivery are deliberately blocked;
same-origin application bundles, the service worker and proxied Umami analytics
continue to work. `style-src 'unsafe-inline'` remains narrowly necessary for dynamic
React layout dimensions and canvas animation, but script execution receives no
equivalent exception. The production smoke test compares the complete learner CSP
to its reviewed contract, and the isolated Nginx test rejects any reintroduced
Cloudflare Insights origin.

The dominant STRIDE risks were tampering through a compromised vendor asset and
information disclosure from browser telemetry. Their blast radius covered every
active learner session, although the current public application has no accounts,
authentication cookies or private learner records. No vendor, credential, personal-
data flow or regulatory scope is added. Detection is immediate in CI or production
smoke; rollback is the backed-up Nginx snippet followed by syntax validation and a
reload. Cloudflare account-side deactivation remains an operational cleanup because
the edge may still add blocked markup. No FAIR loss estimate is asserted without
business-impact inputs. The CISO verdict is **SHIP** after CI, configuration backup,
`nginx -t`, reload and public CSP verification all pass.

### Analytics script integrity and credential boundary — 2026-10-11

The Umami tracker was proxied from a loopback service and executed as a same-origin
script. This avoided an external network origin but still trusted mutable analytics
bytes with the learner page's JavaScript authority. The proxy also inherited browser
request headers and accepted upstream response headers, so a future learner cookie or
authorization token could cross into analytics and a compromised service could set a
cookie, issue an authentication challenge or trigger Nginx `X-Accel-*` behavior.

The reviewed 4,595-byte tracker is now pinned with SHA-384 Subresource Integrity.
Browser E2E proves altered bytes do not execute, and the scheduled production smoke
hashes the live `/u/script.js` response against the HTML metadata. The shared
analytics proxy boundary clears cookies, authorization and common CSRF headers;
suppresses cookies, challenges, redirects and upstream CSP; and disables processing
of response-controlled accelerated redirects, rate, buffering, charset and cache
signals. The collection response is forced to `no-store` with a deny-all document
CSP. A tracker upgrade therefore fails closed until its diff and new digest are
reviewed and released.

The dominant STRIDE risks were supplier tampering, credential information disclosure
and spoofing through same-origin response state. The current application has no
public identity or authentication cookie, which bounds present impact, but the
control prevents silent scope expansion if either is introduced. The blast radius of
malicious tracker execution was every active learner tab; failed integrity now affects
analytics only. CI, browser E2E and six-hour public smoke provide detection. Rollback
uses the retained frontend release and backed-up Nginx vhost/snippet, though restoring
an unpinned tracker is not the preferred recovery. No new vendor, credential,
personal-data flow or regulatory scope is introduced, and no FAIR estimate is claimed
without business loss inputs. The CISO verdict is **SHIP** after hash verification,
CI, configuration backup, syntax validation and public smoke pass.

### Failed backend cutover recovery — 2026-10-11

The backend deploy retained the exact old image and a verified database dump, but
an error after `docker compose up` left the candidate container in place. A failed
healthcheck, weakened runtime isolation, Django warning, unexpected migration state
or question-bank audit could therefore extend an availability incident until a
manual operator rollback, despite the correct recovery artifact already existing.

For releases with no pending migration, those post-cutover checks now form one
rollback boundary. Failure retags the retained image as the live backend image,
recreates only that service with builds disabled, verifies its image/runtime and
Django/migration posture, and requires the old `X-PCEP-Release` through the public
endpoint. The deploy still returns failure so restoration cannot be mistaken for a
successful release. It reports combined candidate and rollback diagnostics if the
recovery itself fails. Final edge-only verification remains outside this automatic
boundary because replacing a locally healthy backend cannot repair DNS, tunnel or
edge policy.

The dominant STRIDE risk is denial of service. Blast radius is the public API and
every active learner needing new questions or grading; static shell availability
does not make a failed API release acceptable. CI unit tests exercise both the
successful recovery path and the migration gate. Automatic application rollback
is refused after reviewed migrations because schema compatibility is not provable;
the retained image and mode-0600 database backup instead anchor the existing manual
runbook. No vendor, credential, personal-data flow or regulatory scope changes, and
no FAIR estimate is claimed without business loss inputs. The CISO verdict is
**SHIP** after CI and the next routine no-migration deployment exercises the normal
success path without invoking recovery.

### CISO go-live decision — 2026-10-13

**Verdict: 🟡 SHIP WITH GUARDRAILS for a controlled real-learner launch.** This is
not an assertion that the service is risk-free, highly available or ready for an
unbounded promotion. The current product has no learner accounts, payment flow,
server-side learner progress or public operator login. Quiz progress, bookmarks and
notes stay in the learner's browser. Do not add accounts, server-side learner data,
payments, an operator UI or an externally fetched URL without a new threat model and
go-live review.

The final 2026-10-13 gate passed 396 backend and 319 frontend tests, all browser E2E
flows, lint, formatting, production build, Django deploy checks, Python/npm audits,
registry-signature verification, tracked/history secret scanning, CodeQL,
GitGuardian, dependency review, isolated Nginx contracts and the complete public
production smoke. GitHub run `38424475501` then passed the same public contract from
outside the host on `main` revision `ebd9328`. Dependabot and code-scanning reported
zero open alerts. The only untracked worktree path was the operator-owned `.claude/`
directory and it was never staged.

The capacity floor is deliberately narrower than a load-test claim. A loopback-only,
GET-only probe passed 50/50 responses at 5 requests/second and 450/450 at 15
requests/second, with zero 429/5xx/timeout, p95 13.777 ms in the sustained run and
stable container memory. The public per-source Nginx policy is now 10 requests/second
with a 60-request burst, followed by the reviewed no-store JSON 429 response. This
supports ordinary use and a shared-NAT classroom start below the measured floor; it
does not model a distributed attack, large future data set or launch event.

The top three remaining STRIDE risks, ordered by qualitative likelihood multiplied
by impact, are:

| Priority | Scenario and blast radius | Detection and response evidence | Residual decision |
| --- | --- | --- | --- |
| 1 — high | **Denial of service/data loss:** physical-host loss, distributed traffic or a shared-host incident can remove the API and every same-host backup. All active learners lose API access, but browser-local progress remains local and the reviewed question bank is reconstructible from source. | The public contract runs twice hourly and opens one sanitized issue. Backup health is published hourly and fails the public contract when degraded or stale. A real isolated restore recovered 308 questions, 1,232 choices and 29 migrations. | Accept only for controlled launch. Do not claim HA or durable offsite recovery. Activate the reviewed encrypted offsite path only after every gate in `OFFSITE_BACKUP_RUNBOOK.md` closes. |
| 2 — high | **Tampering/information disclosure after host compromise:** root on the shared host can read application/database secrets, alter frontend/API bytes and forge the public recovery status. The current database blast radius is the question bank/schema rather than learner accounts; malicious frontend publication could affect every active learner tab. | Release hashes, SRI, request/release IDs, external smoke, CodeQL, secret scanning and least-privilege containers reduce or detect narrower failures. They do not independently attest a root-compromised host. Incident steps and credential rotation exist; the prior application credential exposure was contained and rotation-tested. | Accept only while the no-account/no-PII scope holds. Revisit before storing any learner identity or private server data, and move the attestation or audit evidence off-host before relying on it for compromise detection. |
| 3 — medium | **Supply-chain/browser runtime tampering:** a compromised dependency, analytics byte stream or Python runtime could reach all active browser sessions. | Hashed Python locks, script-free npm installation, exact lifecycle allowlisting, registry signatures/attestations, pinned images/actions/runtime hashes, consent-gated analytics and tracker SRI fail closed in CI/E2E/public smoke. | Residual vendor compromise remains. Continue scheduled advisory scans and require full review for every pin/digest change. |

The workflow requests the public contract twice hourly, but GitHub can delay or drop
scheduled runs, so external detection has no guaranteed upper bound. Local hourly
operations health remains the bounded same-host machine signal for its configured
freshness windows. Guaranteed human MTTD remains unbounded until the repository
owner confirms that an exercised issue reaches a human-controlled email/mobile
channel.
The post-install exercise opened issue #68 assigned to and explicitly mentioning the
repository owner; the next healthy run closed it after the full contract passed.
This proves the technical GitHub-side creation, routing and recovery path but not
delivery through the owner's email/mobile notification settings.

The incident posture has more than paper evidence: the application credential was
rotated after an accidental transcript disclosure, backup restoration was performed
in a network-isolated disposable database, the alert path was exercised end to end
through issue creation/recovery, and deployment retains tested rollback artifacts.
The remaining human tabletop must cover loss of the host/provider credentials,
alert ownership, decision authority, communications and restoration on replacement
infrastructure. It is a launch guardrail, not evidence already completed.

No defensible annual loss expectancy is available because the owner has supplied no
revenue, downtime-cost, response-cost, contractual-penalty or incident-frequency
inputs. Do not invent one. Current regulatory scope is deliberately small: no
learner identity or progress is stored server-side, analytics is opt-in with a
published notice and 180-day retention, and no payment or health data is processed.
If personal data is later added, re-evaluate controller/processor obligations,
retention, data-subject handling and the GDPR breach-notification analysis before
deployment; this review is not a compliance certification.

Cloudflare remains the edge/tunnel provider, GitHub Actions/issues provide external
CI and technical monitoring, and Umami is a loopback analytics service. Google Drive
and Cloudflare R2 are reviewed offsite candidates only; neither is active or approved
by this decision. The Python runtime is shipped as pinned static browser assets on a
separate origin. A supplier failure can still affect availability even where content
integrity is pinned.

Accepted risks require an owner and a revisit trigger:

| Risk owner | Accepted residual | Revisit deadline or trigger | Acceptance rationale |
| --- | --- | --- | --- |
| Repository/production owner | No independently controlled off-host recovery copy | 2026-10-27, or before any non-reconstructible/server-side learner data is stored, whichever comes first | Current learner state is browser-local and the question bank is source-controlled; host-loss availability remains explicitly unprotected. From the deadline, missing/stale offsite success automatically degrades public health and opens the technical alert. |
| Repository/production owner | Human alert delivery is unverified | Before public promotion, or 2026-10-20, whichever comes first | Twice-hourly issue creation is proven, but unattended operation is not acceptable without a named responder receiving the alert. |
| Repository/Cloudflare owner | Previously cached `/static` objects can remain edge-visible after origin retirement | Re-evaluate by 2026-11-12, or earlier after a verified hostname-and-prefix-scoped purge | Both origin route families now fail closed and cannot refill the cache. The external contract automatically adds the known legacy object at the deadline; no media object was present. |
| Production owner | Runtime backend bridge still permits outbound connections | Before adding any server-side URL fetch, webhook, account data or higher-value secret | An isolated Docker fixture proved this engine drops the loopback published port on an `internal` network. A sidecar/Unix-socket redesign is not justified for a backend with no outbound request feature. |
| Product/production owner | Capacity evidence covers only a small read-only workload | Before a marketing event, material database growth or a worker/query/container-limit change | The tested floor exceeds the current per-source limit and ordinary anonymous flows, but cannot establish fleet-wide concurrency or distributed-abuse capacity. |

The controlled launch should stop and roll back if the public smoke fails, the
operations status becomes degraded/stale, a HIGH/CRITICAL fixable runtime advisory
opens, error/latency behavior exceeds the documented capacity gate, or the product
scope crosses any boundary above. Until human notification and off-host recovery are
proven, the owner must actively inspect GitHub production-smoke results and local
timer health; this is the operational cost of accepting the 🟡 verdict.

### Static/media origin retirement — 2026-10-13

The learner application has no Django admin, uploads, templates or dynamic static
consumer, but Nginx still exposed retained Django static artifacts and an empty media
tree. Both the exact and descendant `/static` and `/media` routes now use one hardened
404 policy with `no-store`, a deny-all document CSP, the shared security headers and
a request ID. Host artifacts remain untouched for rollback evidence. An isolated
test mounts sentinel content at both former alias roots and proves it cannot be read;
the twice-hourly public contract probes previously nonexistent canary objects so an
old CDN entry cannot mask origin drift.

The dominant STRIDE risks were information disclosure from unintentionally retained
content and tampering through a future file placed in a public alias. Their origin
blast radius is now eliminated; the remaining edge blast radius is limited to
generated, public Django static files cached before cutover. No media object, secret,
learner record or answer data was found in scope. A cached legacy static response can
survive its original 30-day TTL, but origin retirement prevents refill. The phase-two
deadline is 2026-11-12, when representative legacy URLs become strict public 404
checks unless a narrower verified purge closes the phase earlier.

CI detects route-policy drift in the isolated Nginx fixture, and production detection
is at most about 30 minutes plus workflow execution. Recovery restores the backed-up
vhost only if a separately reviewed operator origin genuinely requires these assets;
the public learner origin is not an acceptable rollback target. No vendor, credential,
personal-data flow or regulatory scope is added, and no FAIR loss estimate is claimed
without business-impact inputs. The CISO verdict is **SHIP** after PR validation,
configuration backup, `nginx -t`, reload, installation verification and public smoke
all pass.

### Rate-limit log privacy — 2026-10-13

A controlled loopback burst proved that Nginx's default `limit_req` diagnostic wrote
both the real client context and complete request target into its error log: all 35
generated `429` responses retained the harmless query canary. The structured access
log was already query- and IP-free, but did not protect this separate fixed-format
path. Search text can contain personal or sensitive content even though the product
does not require it, so file permissions alone were not a sufficient minimization
control.

The learner vhost now emits routine rate-limit diagnostics at `notice`, below its
`warn` error-log threshold. Each rejected request remains visible by request ID,
method, redacted path, status and duration in the structured access log. The isolated
Nginx regression test forces a query-bearing `429` and fails if that canary appears
in the error log. API request-level upstream errors are likewise kept below the
location's `crit` threshold while their 5xx status remains in the redacted access log
and external monitoring. A separate forced upstream failure proves that boundary.
Other unexpected Nginx failures outside the API can still carry request context; the
mode-0640 logs remain restricted operational data and must not become public CI
artifacts.

The dominant STRIDE risk was information disclosure. The blast radius was every
throttled learner whose query contained sensitive text, bounded to host operators and
members of the local `adm` group rather than public users. Detection is immediate in
CI for this known path; incident response is to restrict the log, assess its bounded
retention and rotate it under the existing policy. The change adds no vendor,
credential or data flow and reduces rather than expands potential GDPR personal-data
retention. No FAIR estimate is claimed without loss inputs. The CISO verdict is
**SHIP** after isolated regression, configuration backup, `nginx -t`, reload and a
repeat of the exact live canary test all pass.

### Accepted-risk deadline enforcement — 2026-10-13

Two accepted risks had named dates but depended on an operator remembering to change
monitoring later. The hourly recovery publisher now requires a strict, private and
fresh offsite-success marker beginning at `2026-10-27T00:00:00Z`. Missing, malformed,
unsafe or older-than-24-hour evidence publishes only generic `degraded` state and
exits nonzero. The external smoke already fails on that state, so its deduplicated
incident path activates without exposing remote names, backup names, hashes or error
details. This does not configure rclone, upload data or waive the provider/OAuth,
immutability, recovery-key, DPA and first-restore gates.

The same external smoke always checks uncached static/media canaries and, beginning
at Bucharest midnight on 2026-11-12, automatically requires the known legacy Django
CSS URL to return the hardened 404 contract. A still-cached edge response therefore
becomes an alert instead of a forgotten exception. Both transitions are unit-tested
immediately before and at their boundary dates.

The dominant STRIDE risks are denial of service/data loss after host failure and
repudiation of an expired risk acceptance. The first can remove the API and all local
backups; the second can leave obsolete edge content reachable. Enforcement reduces
detection time to the hourly publisher plus the twice-hourly external poll, but it
does not create offsite durability or prove human receipt. Response remains the
reviewed offsite activation/restore runbook or a narrowly scoped cache purge, with
rollback only for a defective checker—not to extend an expired acceptance silently.
No new vendor, credential, personal-data flow or regulatory scope is introduced, and
no FAIR estimate is claimed without loss inputs. The CISO verdict is **SHIP WITH
GUARDRAILS** after tests, reviewed unit installation, a pre-deadline healthy run and
external production smoke pass.

### Database privilege-drift detection — 2026-10-14

The live database passed the complete least-privilege audit: the application login
cannot own or create database/schema objects, temporary objects, roles or databases;
cannot truncate, reference, trigger, replicate, bypass row security or act as
superuser; and receives only the reviewed table DML and sequence runtime grants.
The non-login owner and normally disabled migrator retain the exact reviewed
membership, ownership and default-grant posture. Previously this full control ran
only at backend deploy, leaving an unbounded detection gap between releases.

An hourly, networkless systemd check now runs the same read-only audit through the
existing local Docker socket and refreshes only a private atomic success marker.
The operations-health publisher requires that marker to be no more than two hours
old; missing, malformed, unsafe, stale or failed evidence produces only the existing
generic public `degraded` state. The external smoke and incident-issue path consume
that state. Technical database-drift MTTD is therefore bounded to roughly two to
three hours for the public signal, plus the external poll; guaranteed human MTTD
still depends on the separately accepted notification-delivery risk. Because the
check uses the existing Docker-authorized host user and its marker is same-host, it
does not claim to detect or attest a compromised host/operator identity.

The top STRIDE risks are tampering with question-bank data, elevation from the
runtime login to schema ownership and repudiation of an unrecorded privilege change.
A fully compromised application role can still alter or delete the 308-question
public bank through required DML, affecting every learner, but cannot alter schema,
roles or the database itself. Response follows the existing incident runbook:
isolate the backend, preserve evidence, rotate credentials, restore exact grants and
validate a backup before reopening. No learner account, server-side progress,
payment or health data enters scope; if personal data is introduced, the GDPR
72-hour assessment and the whole threat model must be revisited. No vendor or DPA is
added. A defensible FAIR/ALE value remains unavailable without business loss inputs.
The CISO verdict is **SHIP** after tests, live role verification, timer installation,
fresh-marker publication and external smoke all pass.

### RFC 9116 vulnerability disclosure — 2026-10-14

The standard `/.well-known/security.txt` URL previously returned the generic SPA
shell with HTTP 200 and `text/html`. A researcher following the conventional
discovery path therefore received no private reporting instructions even though
GitHub private vulnerability reporting was enabled. The release now contains a
bounded RFC 9116 document whose only contact is the private-advisory form, plus a
canonical URL, repository policy, preferred languages and a mandatory expiry. An
exact Nginx location serves only that file as cookie-free `text/plain` with a
deny-all CSP and no-store caching. The service worker cannot turn the path back into
an SPA navigation.

The top STRIDE risks are repudiation through an undiscoverable or expired reporting
channel, spoofing through contact-link drift and information disclosure when a
researcher is diverted to a public issue. The immediate technical blast radius was
one discovery route and every prospective reporter; it exposed no learner record,
credential, database row or regional system. A delayed future report could affect
all users and production assets implicated by that vulnerability, but there is no
incident-frequency or loss-impact evidence from which to claim a FAIR annual loss
expectancy.

Build validation makes the document a mandatory release artifact and permits no
other hidden resource. The atomic publisher safely seeds it into the pre-swap live
tree, so both first-deployment rollback copies retain the channel; hostile symlinks
abort before backup or swap. Isolated Nginx tests verify exact bytes, media type,
headers, cookie absence and method restriction. The external smoke verifies the private
contact, canonical policy, field order and an expiry between 30 and 365 days away on
its twice-hourly schedule. The lower bound creates a renewal incident before the
document becomes stale; technical MTTD is about 30 minutes plus workflow execution.
It opens the existing deduplicated incident issue; guaranteed human MTTD remains
limited by the separately recorded notification-delivery gap. Response is
to validate GitHub private reporting, update or replace the contact and expiry,
republish the frontend, reload only a reviewed Nginx change if needed and rerun the
complete public contract. The general incident tabletop and human delivery test
remain outstanding operational exercises, not reasons to leave the discovery path
false.

GitHub is the existing repository and advisory processor; this change adds no
vendor, credential, OAuth scope or public disclosure channel. Reporters are told not
to submit credentials, production data or personal data, but advisory content can
still become restricted incident evidence under the existing retention and response
rules. Account-level DPA and residency terms were not independently revalidated; on
repository/provider offboarding, the `Contact` and `Policy` targets must be replaced
before the old channel is disabled. If a report establishes awareness of a personal-
data breach likely to risk individuals, the existing GDPR Article 33 assessment and
72-hour supervisory-authority clock apply. The CISO verdict is **SHIP** after build,
isolated route tests, CI, configuration backup, deploy and external smoke pass.

### Operational installation-drift detection — 2026-10-14

The reviewed source and live installation previously matched, but that fact was a
manual point-in-time observation. The hourly operations-health service now checks
the complete allowlisted installation: 12 required PCEP unit files, six timer
enablement links with active runtime state and one host-installed SEO generator.
Unexpected PCEP activation links are rejected. Files must be byte-identical to the
repository with exact root ownership and modes; security-relevant parent and
drop-in directories cannot be symlinks or writable by group/others. Unknown PCEP
units/drop-ins fail closed. The optional offsite service and backup drop-in remain
valid only as an entirely absent or entirely exact pair, so this control neither
activates nor weakens the still-gated offsite design.

The top STRIDE risks are tampering with a scheduled unit or generator, repudiation
of an unrecorded host-only change and denial of service by disabling or redirecting
a timer. The direct policy blast radius is 12 unit files, six schedules and one
generator. A missed backup/restore/security check can weaken recovery or privilege
detection for the entire deployment; a modified generator can mispublish the
public practice pages derived from the 308-question bank. The verifier reads no
learner state or production credential and publishes only the existing generic
`degraded` signal.

Normal drift is detected on the next hourly run and consumed by the twice-hourly
external smoke. Disabling the health timer itself leaves the public marker stale,
so technical detection remains bounded to roughly two to three hours including the
external poll. This is machine MTTD only: guaranteed human MTTD remains unbounded
until the separately recorded notification-delivery exercise is completed. A fully
compromised host or repository owner can alter both the implementation and its
evidence, so this is configuration-drift detection rather than an independent host
integrity attestation.

Response is to preserve journals and the suspect files, compare them with the
reviewed commit, restore the exact root-owned installation from the restricted
release backup, reload systemd, run the standalone verifier, restart the health
check and repeat the full public smoke before reopening. The human incident
tabletop remains outstanding and must include malicious timer disablement as well
as host/provider loss. No new vendor, subprocess credential or personal-data flow
is introduced. If an incident nevertheless exposes personal data, the existing
GDPR breach assessment and, where applicable, 72-hour Article 33 clock still apply.
There are no business loss/frequency inputs from which to calculate a defensible
FAIR annual loss expectancy. The CISO verdict is **SHIP** after focused/full tests,
CI, backed-up unit installation, live verifier success and external smoke pass.

### Container-runtime drift and CPU containment — 2026-10-14

Deploy-time checks already proved the backend isolation policy, but there was no
continuous control for a manual recreation, `docker update`, unexpected project
container or foreign member attached to the database network. Both long-running
containers also had 512 MiB memory and 128-process limits but no CPU quota. On the
ten-core host, a runaway three-worker backend or PostgreSQL workload could therefore
consume substantially more shared compute than the small read-only workload needs.
The reviewed steady state now declares two cores for each long-running container
and one for the ephemeral migrator; the existing 15 request/second capacity floor
must be repeated after live application.

An hourly read-only verifier now requires exactly two PCEP project containers and
two PCEP bridge members. It checks healthy state, image/release identity, exact
environment-name allowlists, users, commands, healthchecks, privileges, namespaces,
AppArmor, ports, mounts, log bounds and CPU/memory/PID limits. Database credentials
and the Django secret are parsed only to prove presence; neither values nor Docker
stderr can enter its errors. Operations health publishes only the same generic
`degraded` state, and the external smoke consumes it. Normal runtime drift is
therefore detected within the hourly run plus the twice-hourly external poll;
stopping the health timer itself is caught by marker staleness in roughly two to
three hours. Guaranteed human MTTD remains subject to the open notification-delivery
exercise.

The top STRIDE risks are elevation of privilege through a privileged/root container,
information disclosure through an unintended public database port or mount, and
denial of service through unbounded CPU or a hostile network peer. The immediate
blast radius is two containers, one Docker bridge, the 308-question API and every
active learner; database compromise can affect the complete question bank and
recovery data, but the current product still stores no learner account/progress,
payment or health record server-side. The two-core limits reserve six of ten host
cores for the host, edge/tunnel and unrelated recovery work while remaining above
the measured application demand.

Response is to preserve private Docker/journal evidence, remove or isolate an
unexpected peer, restore the declarative CPU quota and recreate the affected service
only from a reviewed image/Compose release. Database recovery still requires the
verified backup/restore runbook; do not destroy a suspect container before evidence
and recovery state are secured. The incident tabletop must include a malicious
Docker-network attachment and resource-exhaustion scenario. The verifier executes
under the existing Docker-authorized `micu` identity and cannot attest a fully
compromised host or Docker daemon. No vendor, credential, DPA or personal-data flow
is added. If a runtime incident exposes personal data, the existing GDPR breach
assessment and applicable 72-hour Article 33 clock remain mandatory. No defensible
FAIR annual loss expectancy exists without business loss and frequency inputs. The
CISO verdict is **SHIP WITH GUARDRAILS** only after full CI, no-restart CPU rollout,
live runtime verification, capacity smoke and external production smoke pass.

### Django REST Framework security patch — 2026-10-15

The backend moves from Django REST Framework 3.18.1 to 3.18.3. Version 3.18.2
closes three upstream advisories: unbounded work while negotiating very large
`Accept` headers, acceptance of non-text codecs that can expand a small request
after Django's body-size check, and ineffective deletion through `TokenProxy`.
Version 3.18.3 also restores the 3.18.1 ordering behavior after the intervening
bug fix. This application does not install DRF token authentication and explicitly
disables all authentication classes, so the token-deletion advisory has no current
application path. Content negotiation and JSON parsing do apply to every API route.

The top STRIDE risks are denial of service through `Accept` negotiation, denial of
service through post-limit codec expansion, and elevation/spoofing through a token
that an operator believed was deleted. The first two can affect all public API
workers and therefore every concurrently active learner; the third has a current
blast radius of zero authentication tokens because the product creates none. The
database scope remains the 308-question bank and recovery metadata, with no
server-side learner account, progress, payment or health data. Regression tests now
prove that client media-type parsing is capped at 64 tokens and that a bytes-to-bytes
JSON charset is rejected before decoding. Binary-only, hash-locked installation
also excludes the source distributions from the accepted artifact set.

The daily dependency audit gives advisory-database detection a machine MTTD of at
most roughly 24 hours after the advisory becomes indexable; weekly Dependabot is a
second discovery path. Runtime regressions are covered by the twice-hourly external
smoke and hourly operations checks, but guaranteed human MTTD remains unbounded
until the outstanding notification-delivery exercise is acknowledged by a named
responder. If exploitation is suspected, preserve Cloudflare/Nginx and application
logs, temporarily block the offending request shape at the edge, deploy or roll
back only a hash-locked image, and exercise the incident tabletop with both header
fan-out and compressed-body scenarios.

DRF and pip-tools are local open-source build/runtime components: this change adds
no hosted vendor, credential, subprocessor, DPA requirement or personal-data flow.
If an availability incident also exposes personal data, the existing breach
assessment and applicable GDPR Article 33 72-hour notification clock still apply.
No defensible FAIR/ALE estimate exists without incident-frequency and business-loss
inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after full CI, image audit,
controlled backend deployment and external production smoke pass.

### Nginx request-boundary and drift monitoring — 2026-10-15

The learner and isolated-runner vhosts now declare a 1 KiB ordinary request-header
buffer and no more than two 8 KiB large-header buffers on both HTTP and HTTPS.
Previously the effective single-field bound came from Nginx's platform default;
making it repository policy prevents an image/package default or manual tuning from
silently expanding pre-application work. The isolated contract proves that a 7 KiB
field reaches the upstream fixture and a 9 KiB field is rejected before a Python
worker. This complements, rather than replaces, DRF's independent 8 KiB/64-token
content-negotiation bounds.

The existing exact-file Nginx verifier is now part of the hourly operations health
run. It requires two active vhosts, their exact root-owned activation symlinks and
six root-owned snippets to match the reviewed repository bytes. Any import,
permission, activation or content failure writes only the existing generic public
`degraded` state; private details stay in the system journal. Ordinary drift is
therefore detected within the hourly run plus the twice-hourly external poll, while
stopping the publisher itself becomes visible after the marker's two-hour freshness
window. Guaranteed human MTTD is still unbounded pending the owner-controlled
notification-delivery exercise.

The top STRIDE risks are denial of service through oversized/fragmented headers,
tampering that removes an origin rate/body/header boundary, and information
disclosure if a drifted vhost re-enables a retired or privileged route. The
immediate blast radius is the two public origins, three backend workers and every
active learner; static runner compromise can reach code-execution sessions in the
isolated browser origin but has no server credential. Response is to preserve the
active files and Nginx journal, compare them with the reviewed release, restore the
root-owned exact copies, run syntax and isolated contracts, reload rather than
restart Nginx, and repeat both local and external smoke. The incident tabletop must
include a malicious vhost edit and header-flood scenario.

No vendor, credential, subprocessor, DPA or personal-data flow is added. A
root-compromised host can forge both configuration and same-host health evidence,
so independent attestation remains a residual risk. If an origin incident exposes
personal data, the existing breach assessment and applicable GDPR Article 33
72-hour clock remain mandatory. No defensible FAIR/ALE estimate exists without
frequency and business-loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS**
after full CI, backed-up root installation, isolated/live verification, Nginx reload
and external production smoke pass.

### Scheduled-service syscall containment — 2026-10-15

All seven repository-owned systemd services now use the positive
`@system-service` syscall set and return `EPERM` for denied calls. The five
networkless worker services also combine their existing private network namespace
with `IPAddressDeny=any`; the health publisher changes its default umask from 0027
to 0077 while retaining the explicit mode-0600 marker and named Nginx ACL. The
networked analytics and optional offsite services keep only their already reviewed
loopback/public address policies. Repository validation fails if any service loses
the syscall controls or a networkless unit loses its IP deny.

Compatibility was exercised with a real Docker-socket database-role audit, a
loopback Umami retention transaction that was explicitly rolled back, and the
installed Go rclone binary. On systemd 259 the offline exposure scores fall from
2.1–2.7 to 0.6–1.6 across the seven definitions; these scores are a comparative
hardening signal, not proof of isolation. The hourly installation verifier now also
rejects a failed state for every installed scheduled PCEP oneshot except its own
currently executing publisher. A timer can therefore no longer appear healthy
while its most recent analytics, backup, restore, database-security or SEO job is
failed.

The top STRIDE risks are elevation of privilege through an unnecessary kernel
interface, tampering or data loss after a failed maintenance job is overlooked, and
denial of service from an allowlist that blocks a legitimate runtime call. The
direct policy blast radius is seven service definitions and six enabled schedules;
the operational blast radius includes the two public origins, all 308 questions,
local recovery copies and the bounded Umami data set. A denied call fails the job
immediately and enters its private journal. The hourly publisher detects retained
failed states, and the external poll consumes the generic result; normal machine
MTTD is therefore roughly one hour plus the poll, or two to three hours if the
publisher itself stops. Guaranteed human MTTD remains unbounded pending notification
delivery confirmation.

Response is to preserve the unit journal and exact installed bytes, distinguish a
malicious policy change from a legitimate `EPERM`, and restore the prior reviewed
unit before `daemon-reload` if compatibility is not proved. The incident tabletop
must include both a hidden failed timer job and an attempted forbidden syscall. No
vendor, credential, subprocessor, DPA or personal-data flow is added. If an incident
exposes personal data, the existing breach assessment and applicable GDPR Article
33 72-hour clock remain mandatory. No defensible FAIR/ALE estimate exists without
frequency and loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after full
CI, backed-up unit installation, representative live service runs, improved live
exposure scores, healthy operations publication and external smoke pass.

### Restore-drill startup cleanup — 2026-10-15

A controlled restore run exposed a Docker failure mode in which the daemon created
and ran the disposable database container but the detached client did not return
before its 60-second timeout. The previous context manager had not yet reached its
cleanup block, so the dead named container remained and would have made every later
scheduled drill fail on a name collision. Startup and interrupted-body failures now
perform best-effort cleanup as well as the existing successful path. Cleanup first
requires the exact drill label and expected immutable image ID, then removes the
container by its validated 64-hex-character ID. It refuses an unlabelled,
same-named or different-image container.

The top STRIDE risks are denial of service from an orphan blocking future recovery
tests, tampering or destructive cleanup through deliberate container-name squatting,
and repudiation or false recovery confidence when no new success marker can be
written. The direct cleanup blast radius is one disposable, networkless container
and one weekly schedule. The recovery-confidence blast radius includes the newest
local backup and all 308 questions it should restore; neither cleanup nor the drill
connects to or removes the production database, backup files or application
containers.

A failed service state is retained immediately. The hourly health publisher checks
both that state and the bounded-age success marker, and the twice-hourly external
smoke consumes the generic result, giving normal machine MTTD about one hour plus
the poll, or two to three hours if the publisher itself stops. Guaranteed human
MTTD remains unbounded until notification delivery is confirmed. Response is to
preserve the service and Docker journals, inspect label/image/ID without printing
environment values, remove only a proven drill container, rerun the isolated restore
and then republish health. The incident tabletop must exercise both a client timeout
after daemon-side creation and a hostile same-name container.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
incident exposes personal data, the existing breach assessment and applicable GDPR
Article 33 72-hour clock remain mandatory. No defensible FAIR/ALE estimate exists
without incident-frequency and business-loss inputs. The CISO verdict is **SHIP
WITH GUARDRAILS** after focused and full tests, live restore/cleanup verification,
fresh healthy publication, full CI and external production smoke.

### Disposable audit-resource ownership — 2026-10-15

The disposable PostgreSQL runtime validator previously derived its container and
volume names from the shell PID and its exit trap attempted to remove both names
even when creation had not been proven. A reused PID, pre-existing resource or
interrupted create could therefore make a validation run touch an unrelated test
resource or leave its own resource behind. Each run now generates a 128-bit token,
places it in an explicit ownership label on both resources, captures and validates
the full container ID, and makes the trap re-inspect label plus identity before any
removal. The stop/start persistence test remains intact.

The isolated Nginx contract had the complementary interruption edge: its
long-running `--rm` container was removed by a captured ID, but an interruption
after daemon-side creation and before shell assignment could leave it running on a
random loopback port. It now uses a separate validated 128-bit ownership token; the
trap lists only that exact label, validates every full ID, re-inspects the label and
removes the proven container. Its temporary directory has a dedicated prefix and
must be a real, non-symlink directory with the exact generated shape before
recursive deletion.

Both traps preserve the primary nonzero result on a failed contract, while emitting
a private cleanup warning. If the contract itself passed, a removal error, unsafe
temporary path, failed follow-up inventory or any resource still carrying the run
token changes the final result to failure. Cleanup is therefore an asserted part of
the validation rather than a best-effort side effect.

The top STRIDE risks are tampering through deletion of a same-named foreign
resource, denial of service from an orphan consuming host resources, and information
disclosure from leaving the synthetic test credentials/data accessible to another
Docker-authorized process. The direct blast radius is the one unpublished
PostgreSQL container bounded to 512 MiB and 128 PIDs, its one synthetic-data volume,
and the isolated Nginx fixture on a random loopback port with generated certificates
and public test assets. Neither path has a production volume, public listener or
production database credential, so the 308-question production database is outside
the direct path.

Standard success, failure and interrupt paths detect and clean their resources
before the command exits, and pull-request CI reruns the complete validator. A
`SIGKILL`, daemon loss or host crash can still leave a labelled resource, for which
guaranteed human MTTD is unbounded. Response is to preserve Docker events, list only
the exact ownership label, inspect label/name/ID, and remove the confirmed test
resource without a broad prune. The incident tabletop must cover both deliberate
name collision and interruption between daemon-side creation and client response.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host incident exposes personal data, the existing breach assessment and applicable
GDPR Article 33 72-hour clock remain mandatory. No defensible FAIR/ALE estimate
exists without frequency and business-loss inputs. The CISO verdict is **SHIP WITH
GUARDRAILS** after shell validation, complete PostgreSQL and isolated Nginx runtime
contracts, proof that no labelled resource or temporary tree remains, full CI and a
clean image audit.

### Destructive-operation serialization — 2026-10-15

Backend deployment and rollback-image retention previously validated Docker state
independently without serializing the interval between inventory and tag/build/
removal. Two deployments, or a deployment overlapping retention, could therefore
act on different generations while each command believed its earlier view was
current. The one-time database-role separation could also overlap these operations
while changing the same role posture. Frontend publication and release-snapshot
retention had the analogous gap around live-root exchange and recursive snapshot
removal.

The five operations now use non-blocking advisory locks in a dedicated
`/run/lock/pcep-<uid>` directory. Backend deployment, database-role separation and
image retention share one host-global key. Frontend publication and snapshot
retention derive a key from the canonical live-root path, so aliases of one target
collide while unrelated targets remain independent. The lock directory and file
are fail-closed unless they are real, owner-matched and private (`0700`/`0600`);
symlinks, unsafe names, concurrent holders and permissive modes are rejected before
the protected operation. Kernel descriptor lifetime releases a lock on every
ordinary exit, exception or killed process without treating the persistent file as
evidence of an active holder.

The top STRIDE risks are tampering when a rollback tag or snapshot changes after
validation, denial of service when two Compose cutovers or directory exchanges
interleave, and repudiation/recovery-integrity loss when the retained rollback no
longer corresponds to the operation that reported it. The direct backend blast
radius is one service with three workers, the six currently inventoried rollback
tags and the pre-deploy copy of the 308-question database. The direct publication
blast radius is one live release root, both public origins that consume its bounded
assets, and the current rollback/backup generations. The control does not itself
read or transmit learner data, credentials or backup contents.

A cooperating concurrent invocation is detected synchronously before its first
Docker or live-filesystem mutation, so machine and interactive-operator MTTD are
effectively immediate. The refusal is written to the invoking private terminal or
service journal. Commands that bypass these reviewed scripts remain outside the
lock protocol; hourly operations health and twice-hourly external smoke can detect
some resulting availability drift, while guaranteed human MTTD for an unalerted
manual bypass remains unbounded until notification delivery is confirmed.

Response is to preserve both command outputs and process inventory, identify the
legitimate holder, allow it to finish or terminate that exact process after review,
then rerun inventory and the refused operation. Never remove the persistent lock
file as a concurrency workaround. The tabletop cases are two simultaneous backend
deployments, deploy versus image retention or database-role separation, two
frontend publishers, and publisher versus snapshot retention; automated regressions
now prove refusal before Docker, PostgreSQL inspection or live-root access for both
resource families.

No hosted vendor, credential, subprocessor, DPA or personal-data flow is added. If
a wider concurrency incident causes personal-data compromise, breach assessment
and the applicable GDPR Article 33 72-hour notification clock remain mandatory.
No defensible FAIR/ALE estimate exists without incident frequency, active-user and
business-loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused and
full tests, live private-lock validation, both production dry-runs, full CI and
external production smoke.

### Restore-drill concurrency ownership — 2026-10-15

The restore drill's startup-timeout cleanup previously proved only a generic drill
label plus the expected image and fixed container name. Two legitimate overlapping
runs therefore looked identical: when the second `docker run` failed on the name
collision, its recovery path could inspect and remove the first run's active
container. The systemd timer serializes its own unit, but it does not serialize a
simultaneous manual invocation.

Scheduled and manual drills now share a non-blocking lock in the service's private
mode-`0700` state directory. Each admitted run also generates a distinct validated
128-bit token and places it in the Docker ownership label before creation. Every
success, body-failure and startup-timeout cleanup requires that exact token, the
expected immutable image ID and a valid full container ID before removal. A
same-named container carrying another legitimate run's token is explicitly refused,
preserving defense in depth if a caller bypasses the cooperating lock.

The top STRIDE risks are tampering through cross-run deletion, denial of service
when the weekly recovery proof is interrupted or blocked, and repudiation/false
recovery confidence if one run reports another run's resource state. The direct
blast radius is one networkless disposable container bounded to 768 MiB and 128
PIDs. The recovery-confidence radius is the newest verified daily backup and all
308 questions it must restore; the production database, application containers and
backup files are never removal targets.

A cooperating collision is detected synchronously before backup or Docker
inspection, giving immediate machine and interactive MTTD. Token mismatch is also
detected during cleanup and retained in the private unit journal. The hourly health
publisher and twice-hourly external poll detect a failed scheduled result or stale
success marker in roughly one to three hours, but guaranteed human MTTD remains
unbounded until notification delivery is confirmed.

Response is to preserve both journals/command outputs, inspect only label, image and
immutable ID without printing environment values, let the legitimate holder finish,
then rerun the refused drill and republish health. Never delete an active lock or
remove a mismatched container. The incident tabletop must cover timer versus manual
invocation, startup timeout after daemon-side creation, and a same-name container
with another valid drill token.

No vendor, credential, subprocessor, DPA or new personal-data flow is added. If a
wider incident exposes personal data, breach assessment and the applicable GDPR
Article 33 72-hour notification clock remain mandatory. FAIR/ALE cannot be defended
without incident-frequency, active-user and business-loss inputs. The CISO verdict
is **SHIP WITH GUARDRAILS** after focused/full tests, exact live service execution,
healthy publication, full CI and external production smoke.

### Crash-durable deployment backups — 2026-10-15

The deploy gate previously closed and validated the compressed PostgreSQL dump,
atomically renamed it into place and calculated its SHA-256, but did not explicitly
flush the file or parent directory before allowing image build and cutover. A host
reset or storage/power failure in that interval could therefore leave the reported
rollback backup missing or incomplete even though the process had observed valid
bytes in page cache.

The shared backup implementation now fsyncs the completed mode-`0600` dump after
full decompression/header validation and digest calculation, then fsyncs the private
backup directory so the rename is durable. Any flush failure aborts deployment
before candidate build, migration activation or service replacement. Daily backups
retain their independent checksum-sidecar fsync sequence; its extra file flush is
intentionally harmless defense in depth.

The top STRIDE risks are tampering/data loss through non-durable recovery evidence,
repudiation when a deploy reports a backup that does not survive a crash, and denial
of service if recovery must proceed without the promised pre-cutover snapshot. The
direct blast radius is one deployment backup and the current 308-question database;
the running database and retained older daily/pre-deploy backups are not modified by
the new flush operations.

An fsync or directory-open failure is synchronous and stops the deploy, giving
immediate machine/operator MTTD. Latent storage faults remain covered by daily
checksum verification and the weekly isolated restore, with hourly/twice-hourly
machine publication; guaranteed human MTTD remains unbounded until notification
delivery is confirmed. Response is to preserve the filesystem/kernel journal,
quarantine the affected backup, run storage diagnostics, create and isolate-restore
a new dump, and only then retry deployment. The tabletop must include power loss
after rename and explicit file/directory fsync failure.

No vendor, credential, subprocessor, DPA or personal-data flow is added. A wider
failure that exposes personal data still requires breach assessment and the
applicable GDPR Article 33 72-hour notification clock. FAIR/ALE is not defensible
without storage-failure frequency and business-loss inputs. The CISO verdict is
**SHIP WITH GUARDRAILS** after focused/full tests, a real durable backup probe, full
CI and external production smoke.

### Crash-durable static publications — 2026-10-15

The frontend/static publisher and the host SEO generator previously made their
namespace changes atomically, but atomic visibility alone did not prove that newly
copied file data and child-directory entries had reached stable storage. The SEO
path flushed only the live parent after exchange; the general publisher did not
flush the staged tree, backup or parent. A power loss after a reported success
could therefore reveal an incomplete release after reboot, or remove the external
snapshot that an operator expected to use for rollback.

Both publishers now fsync every validated regular file with no symlink following,
then every directory from the deepest child through the staged root before the
first live-root exchange. The frontend/static publisher also flushes its complete
external snapshot and backup root, the live parent immediately after exchange, and
the parent again after assigning the retained rollback name. The first-deployment
rename follows the same tree-before-parent order. The RFC 9116 disclosure seed is
flushed before its atomic replace and its `.well-known` directory is flushed after
it. SEO removes its old tree only after the durable cutover and separately flushes
that cleanup. A pre-cutover flush error removes only staging and leaves the live
root unchanged; a post-exchange error preserves the old root and reports that the
operation did not complete durably.

The top STRIDE risks are tampering/data-integrity loss through partially durable
public bytes, denial of service when a reboot exposes a missing shell, worker or
SEO tree, and repudiation/false recovery confidence when a command reports a
snapshot or rollback root that storage did not retain. The direct frontend blast
radius is one live release, one new external backup and one immediate rollback
root consumed by two public origins. The SEO radius is one eight-file generated
tree representing the current 308-question public corpus. Active learner-tab and
crawler counts are not measured, so their numeric business radius is unknown.

File, directory-open and fsync failures are synchronous, giving immediate machine
and invoking-operator MTTD before cutover whenever possible. A latent storage fault
visible only after reboot should fail the next external public contract, but GitHub's
requested twice-hourly schedule can be delayed or dropped, so guaranteed external
and human MTTD remain unbounded. Response is to preserve the command, kernel and
filesystem journals,
avoid pruning either retained tree, validate both live and previous roots, republish
the last verified snapshot, and rerun public/origin smoke. The tabletop must cover
file fsync failure before exchange, parent fsync failure immediately after exchange,
and power loss between cutover and rollback-root rename.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
storage or host incident exposes personal data, breach assessment and the applicable
GDPR Article 33 72-hour notification clock remain mandatory. FAIR/ALE is not
defensible without storage-failure frequency, active-user and business-loss inputs.
The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full regression tests, a
real two-generation publication probe, live SEO regeneration, full CI and external
production smoke.

### Private operations-health diagnostics — 2026-10-15

Operations health correctly published only a generic three-field `degraded` marker,
but its three verifier wrappers also discarded the underlying installation, Nginx
or container-runtime exception before the service journal was written. The live
degraded interval observed on 2026-10-15 demonstrated the operational gap: external
monitoring could identify the unhealthy window, while the retained journal could
not reconstruct which reviewed path, scheduled unit or runtime assertion caused it.

Verifier failures now keep their existing generic category plus the underlying
sanitized verifier message in the private service exception. Control characters and
newlines are collapsed, empty errors fall back to their class name and detail is
bounded to 512 characters. The public marker remains exactly `schema`, `status` and
`checked_at`; tests inject recognizable diagnostic canaries and prove they appear in
the private exception but never in the public file. The verifiers themselves emit
allowlisted paths, unit/container roles and policy assertions, never environment
values, credentials or raw Docker stderr.

The top STRIDE risks are repudiation when failure evidence is discarded, tampering
that remains hard to localize across several attested surfaces, and denial of
service prolonged by diagnosis without an actionable component. The diagnostic
blast radius covers 12 reviewed units, six timers, two Nginx vhosts, six snippets,
two containers and one network. Public disclosure remains three non-sensitive JSON
fields, and no new reader, network route or journal permission is introduced.

The hourly publisher still gives at most roughly one hour machine MTTD for scheduled
drift, while twice-hourly external smoke detects the generic degraded marker in at
most 30 minutes. Once an operator reaches the journal, component-level diagnosis is
available in that same failed invocation instead of being unbounded; guaranteed
human MTTD remains unbounded until notification delivery is confirmed. Response is
to preserve the exact journal and installed bytes, compare only the named surface
with its reviewed source, restore or isolate it, rerun its standalone verifier and
then republish health. The tabletop must cover a unit hash mismatch, a failed
scheduled oneshot, container isolation drift and multiline/oversized exception text.

No vendor, credential, subprocessor, DPA or personal-data flow is added. A wider
incident involving personal data still requires breach assessment and the applicable
GDPR Article 33 72-hour notification clock. FAIR/ALE is not defensible without
incident-frequency, response-time and business-loss inputs. The CISO verdict is
**SHIP WITH GUARDRAILS** after focused/full tests, a controlled private/public
canary, full CI, live health publication and exact-SHA external smoke.

### Crash-bounded daily-backup pruning — 2026-10-15

Daily retention previously unlinked a selected backup checksum before its compressed
dump and flushed the directory only after every pair was removed. If the process,
filesystem or host failed between those two unlinks, the large dump remained without
its sidecar. Discovery intentionally ignores unpaired dumps to avoid deleting
potential recovery evidence, so every such interruption could permanently move one
large file outside the retention bound and eventually exhaust the backup filesystem.

Retention now revalidates that each selected dump and checksum are regular,
non-symlinked members of the exact private root and exact daily naming contract. It
unlinks the large dump first and fsyncs the root before unlinking its small checksum,
then fsyncs the root again before advancing. A crash can therefore produce either
the original complete pair or a small orphan checksum, never a large checksum-less
dump caused by pruning. Existing unpaired dumps remain deliberately untouched.

The top STRIDE risks are denial of service through unbounded disk use, repudiation
when a nominal retention run silently leaves untracked data, and tampering/recovery
confusion around a partially deleted pair. Production currently has 14 complete
daily pairs totaling 814,234 bytes; the largest is 58,318 bytes and no orphan was
found. The configured floor is 30, so this release performs no live deletion. At
larger future database sizes, only the currently processed old pair can be partial
at an interruption; earlier selected pairs are already durably removed, while all
7–365 configured newest retained pairs remain outside deletion.

Unlink or fsync failure is synchronous and fails the daily oneshot, giving immediate
local machine state. The hourly installation verifier also rejects the backup
service's failed systemd state; if that volatile state is reset, the full-job success
marker documented below still ages out independently. The next external smoke can
then observe generic degradation, but its GitHub schedule has no guaranteed delivery
bound, and human MTTD remains unbounded until notification delivery is confirmed.
Response is to preserve the journal and directory inventory, never delete an
unpaired dump automatically,
verify all remaining complete pairs, copy important evidence off-host, restore disk
headroom and rerun backup/restore validation. The tabletop must cover failure after
the dump unlink, checksum unlink failure and power loss before each directory fsync.

No vendor, credential, subprocessor, DPA or personal-data flow is added. A wider
incident involving personal data still requires breach assessment and the applicable
GDPR Article 33 72-hour notification clock. FAIR/ALE is not defensible without
backup-growth, storage-failure and business-loss inputs. The CISO verdict is
**SHIP WITH GUARDRAILS** after failure-injection/full tests, read-only live inventory,
full CI, healthy publication and exact-SHA external smoke.

### Crash-durable release-snapshot pruning — 2026-10-15

Frontend release retention recursively removed each validated old snapshot but did
not flush the directory containing that removed tree. Atomic namespace operations
do not by themselves make the deletion durable. A power, kernel or storage failure
could therefore resurrect a fully or partly removed snapshot after the command had
advanced or reported success, leaving disk use and recovery inventory different
from the reviewed plan.

Every selected tree removal is now followed immediately by an `fsync` of its exact
resolved parent, opened read-only with directory and no-follow protections where
the platform exposes them. An open, type-check or flush failure aborts before the
next tree. Existing allowlists, symlink refusal, current-contract validation,
non-blocking publisher lock and minimum two-valid-snapshot floor remain unchanged.
The live root is never a removal candidate.

The top STRIDE risks are denial of service through unexpectedly persistent release
trees and eventual disk exhaustion, repudiation when reported reclaimed space does
not survive a crash, and tampering/recovery confusion from a resurfaced partial
tree. The read-only production plan found eight rollback roots and eight external
copies: five valid snapshots per location remain protected while three plus three
old candidates totaling 98.7 MiB are eligible. At any interruption, only the one
tree whose removal is in progress can lack a durable outcome; the live release and
the five retained snapshots in each location are outside the deletion set.

An open or `fsync` failure is synchronous and stops the command, giving immediate
machine and invoking-operator MTTD. A crash that exposes latent storage behavior is
visible on the next retention dry-run or disk-capacity check, but no dedicated
snapshot-resurrection alert exists, so guaranteed machine and human MTTD for that
latent case are unbounded until monitoring and alert delivery are confirmed. Live
availability continues to be covered by hourly health and twice-hourly external
smoke, but those signals do not attest old snapshot inventory.

Response is to preserve the command, filesystem and kernel journals, run retention
again without `--apply`, validate live and retained roots, compare only exact
allowlisted candidates, restore disk headroom, then apply the reviewed plan again.
Never use a broad recursive delete or remove an unvalidated tree. The incident
tabletop must cover failure after the first recursive removal, parent-directory
`fsync` failure and power loss before and after that flush.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host incident exposes personal data, breach assessment and the applicable GDPR
Article 33 72-hour notification clock remain mandatory. FAIR/ALE is not defensible
without storage-failure frequency, disk-growth, active-user and business-loss
inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after failure-injection/full
tests, a read-only live inventory, full CI, healthy publication and exact-SHA
external smoke.

### Crash-durable failed-publication cleanup — 2026-10-16

The frontend/static and SEO publishers removed their hidden staging tree after a
pre-cutover failure but did not flush the containing directory. A successful
command-level cleanup could therefore be lost across a host or storage reset. In
addition, an error raised by recursive cleanup could replace the original render,
validation or storage failure, weakening incident diagnosis while repeated hidden
residues consumed disk outside snapshot-retention discovery.

Both publishers now recursively remove failed staging and immediately `fsync` its
exact parent before returning the primary failure. If removal or flushing itself
fails, the original exception remains authoritative, the secondary error is
attached as a note and a separate warning is emitted to stderr/the private service
journal. The live tree is never selected by this cleanup, and all existing atomic
exchange, validation, symlink and non-blocking-lock controls remain in force.

The top STRIDE risks are denial of service through repeated hidden staging and disk
exhaustion, repudiation when cleanup success or the initiating failure cannot be
reconstructed, and tampering/recovery confusion around a partial non-live tree.
The production inventory found zero matching staging residues. A current complete
frontend tree is 15,108 KiB and the SEO tree is 156 KiB, so one failed run has that
approximate direct storage radius; repeated failures were previously unbounded.
The live release, rollback roots, backups and current 308-question database remain
outside the failed-stage cleanup target.

The initiating and cleanup failures are synchronous, giving immediate machine and
invoking-operator MTTD; a failed scheduled SEO unit is also detected by the hourly
operations publisher and twice-hourly external contract in roughly one to three
hours. There is still no dedicated stale-staging inventory alert, so a residue left
by abrupt process or host death has unbounded guaranteed machine and human MTTD
until disk/inventory monitoring and alert delivery are confirmed.

Response is to preserve the publisher, unit, filesystem and kernel journals; retain
the primary and cleanup messages together; validate the live tree; inventory only
the exact hidden staging patterns; recover disk headroom; and republish from a
verified source. Never broad-delete the live parent. The tabletop must cover a
render/validation failure followed by successful durable cleanup, recursive-delete
failure, parent-`fsync` failure and power loss during cleanup.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host incident exposes personal data, breach assessment and the applicable GDPR
Article 33 72-hour notification clock remain mandatory. FAIR/ALE is not defensible
without failure frequency, disk-growth, active-user and business-loss inputs. The
CISO verdict is **SHIP WITH GUARDRAILS** after focused/full failure-injection tests,
zero-residue live inventory, live SEO generation, full CI, healthy publication and
exact-SHA external smoke.

### Stale publication-staging detection — 2026-10-16

Crash-durable cleanup still cannot execute when a publisher process, kernel or host
dies during recursive removal. Frontend/static and SEO staging use hidden temporary
names that bounded snapshot retention deliberately does not select. Without an
inventory signal, each abrupt failure could therefore leave a partial tree until a
manual disk investigation, making machine and human MTTD unbounded.

The hourly operations publisher now reads the real `/var/www/pcep` parent and
recognizes only the exact temporary-name contracts for frontend, static and SEO.
Every matching entry must be a current-user-owned real directory with no group or
other write bit. The newer inode-change or modification timestamp may be no more
than two hours old and no more than five minutes in the future. This tolerates a
legitimate active copy, resists an old source mtime, and fails closed on malformed
prefix matches, symlinks, files or unsafe metadata. The detector is read-only and
never decides that a tree is safe to delete.

The top STRIDE risks are denial of service through undetected disk growth,
repudiation when failed-publication residue has no bounded signal, and tampering
when a planted or metadata-altered staging entry is accepted as ordinary. The live
inventory found zero matching residues. A present complete frontend and SEO tree
measure 15,108 KiB and 156 KiB respectively; one failed run has that approximate
storage radius, while live releases, rollback roots, external snapshots and the
308-question database are outside the detector's write scope because it has none.

After the two-hour tolerance, the hourly publisher gives machine MTTD of at most
roughly one additional hour, or about three hours from staging creation. The
requested twice-hourly external contract sees generic `degraded` only when GitHub
actually starts it; scheduled runs can be delayed or dropped, so external MTTD has no
guaranteed upper bound. The private journal names the exact reviewed candidate while
the public JSON stays at three non-sensitive fields. Guaranteed human MTTD remains
unbounded until alert delivery and acknowledgement are confirmed. A compromised
`micu`/root identity can refresh metadata or forge health, so this is a narrower
failure detector rather than independent host attestation.

The incident-response runbook now requires preserving journals and exact metadata,
checking the publisher process and lock, validating live/rollback/backup trees and
using only a separately reviewed exact-path cleanup after ownership is excluded. It
forbids broad wildcard deletion. The tabletop must cover a legitimate fresh stage,
a stale partial directory, a matching symlink, future metadata and an unexplained
unsafe owner or mode.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host incident exposes personal data, breach assessment and the applicable GDPR
Article 33 72-hour notification clock remain mandatory. FAIR/ALE is not defensible
without failure frequency, disk-growth, active-user and business-loss inputs. The
CISO verdict is **SHIP WITH GUARDRAILS** after focused/full tests, exact unit
installation, a zero-residue live inventory, healthy publication, full CI and
exact-SHA external smoke.

### Crash-durable operations-health temporary cleanup — 2026-10-16

The operations-health publisher wrote and fsynced a private random temporary before
atomic replacement, but its unconditional failure cleanup only unlinked that path.
It did not flush the state directory, and a cleanup error could replace the original
verifier, serialization or storage exception. A host reset could therefore restore
a supposedly removed partial, while the private journal lost the initiating reason
needed to explain why the public health marker stopped advancing.

Pre-replace failure cleanup now unlinks the exact random temporary and immediately
fsyncs the validated state directory. Directory open uses close-on-exec, directory
and no-follow flags where supported, rechecks the opened descriptor type, and always
closes it. If unlink or flush fails, the original exception remains authoritative;
the secondary failure is attached as a note and emitted separately to the private
service journal. A successful replace continues to flush the same directory, and
the existing marker is never edited in place.

The top STRIDE risks are repudiation through loss of the primary health failure,
denial of service when repeated invisible partials consume state storage or block
publication, and tampering/recovery confusion around leftover marker material. The
live inventory found zero matching partials. The current public marker is 63 bytes
and contains only `schema`, `status` and `checked_at`; one in-flight temporary has
that bounded approximate radius, is created mode 0600 inside the private state
directory, and contains no learner, credential, backup or verifier-detail data.

The service failure and separate cleanup warning are synchronous, giving immediate
machine and invoking-operator MTTD. If the public marker cannot advance, the
twice-hourly external contract rejects it once `checked_at` exceeds two hours, so
external detection occurs no later than roughly two hours and 30 minutes after the
last successful publication. Guaranteed human MTTD remains unbounded until alert
delivery and acknowledgement are confirmed.

The incident-response runbook now preserves the primary and cleanup diagnostics,
existing marker/ACL and storage evidence; forbids a hand-written `ok` marker; and
requires correcting the initiating failure before restarting the reviewed service.
The tabletop must cover serialization failure before replace, unlink failure,
directory-`fsync` failure and a stale but still publicly readable prior marker.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host incident exposes personal data, breach assessment and the applicable GDPR
Article 33 72-hour notification clock remain mandatory. FAIR/ALE is not defensible
without failure frequency, response cost and business-loss inputs. The CISO verdict
is **SHIP WITH GUARDRAILS** after focused/full failure-injection tests, zero-partial
live inventory, exact service execution, full CI, healthy publication and exact-SHA
external smoke.

### Bounded pre-deploy backup diagnostics and residue detection — 2026-10-18

The shared deployment dump previously wrote `pg_dump` stderr to a private but
unbounded temporary file. Its finalizer unlinked both dump and error temporaries
without flushing the backup directory, and any process-stop or unlink error could
replace the original dump/validation failure. A process or host crash could also
leave those hidden entries indefinitely because backup discovery intentionally
ignores incomplete material and operations health did not inventory this root.

The dump now accepts only a bounded prefix and exact UTC basic timestamp, creates
its mode-0600 partial with exclusive/no-follow and close-on-exec flags, and drains
stderr concurrently into a fixed 64 KiB in-memory tail. Only the final 2,000 sanitized
characters enter the private exception, and no new stderr file is created. Failed
partial deletion is followed by a validated directory `fsync`; secondary process,
unlink or flush failures are attached to and logged separately from the primary
error. A cleanup failure after successful publication still blocks deployment.

Operations health now inventories the deployment backup root read-only. Only exact
current partial and legacy stderr names enter scope; matches must be private regular
files owned by the service user with a valid timestamp. Fresh matches are tolerated
for two hours to avoid racing a real deploy, while malformed, unsafe, future-dated
or stale entries degrade the same three-field public marker. The verifier neither
opens nor deletes their contents.

The top STRIDE risks are denial of service through unbounded stderr or repeated
hidden partial dumps, repudiation when cleanup replaces the initiating failure, and
information disclosure if private database/error material remains after a crash.
The live inventory found zero matching temporaries. There are 35 complete root-level
database dumps totaling 2,008,322 bytes; the largest current dump is 58,320 bytes.
One in-flight compressed partial can approach the database dump size as the database
grows, while the new stderr memory radius is exactly 64 KiB and its logged tail at
most 2,000 characters. Complete-backup retention requires a separate reviewed policy
and is intentionally not changed or deleted by this control.

A normal cleanup failure is synchronous, giving immediate machine and invoking-
operator MTTD. Crash residue becomes unhealthy after two hours and the hourly timer
with bounded jitter detects it in roughly three hours from creation. The requested
twice-hourly external smoke observes only generic degradation when GitHub actually
starts it; external delivery has no guaranteed upper bound. Guaranteed human MTTD
remains unbounded until alert delivery and acknowledgement are confirmed.

The incident runbook preserves journals, exact metadata, storage evidence and lock
ownership; forbids broad wildcard deletion and public copying of dump/error content;
and requires verifying a complete backup plus isolated restore before retry. The
tabletop must cover an oversized stderr producer, dump failure plus directory-fsync
failure, process death before cleanup and a stale malformed/symlinked entry.

No vendor, credential, subprocessor, DPA or personal-data flow is added. The current
database contains the reconstructible question bank rather than learner accounts;
if future scope introduces personal data, exposure requires breach assessment and
the applicable GDPR Article 33 72-hour notification decision. FAIR/ALE cannot be
defended without database-growth, failure-frequency, response-cost and business-loss
inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full failure-
injection tests, zero-residue live inventory, exact unit installation, full CI,
healthy publication and exact-SHA external smoke.

### Final-PostgreSQL readiness after restore alert — 2026-10-18

The scheduled isolated restore failed at `2026-10-18T00:33:20Z` after
`pg_isready` returned success against the temporary PostgreSQL server used by the
official entrypoint during first-boot initialization. That server then stopped so
the entrypoint could exec the final server, and the immediately following `psql`
role-preparation command received `FATAL: the database system is starting up`. The
drill correctly preserved its previous success marker, removed its owned disposable
container and left production data untouched, but the service remained failed and
operations health correctly published generic `degraded`.

Three scheduled public-smoke runs failed on that state and the first opened
deduplicated issue #100. A controlled rerun completed the full restore at
`2026-10-18T13:17:50Z`; health returned to `ok`, external run `39130932755` passed
and automatically closed the issue. This was a real monitoring/control failure, not
a learner-origin or production-database outage.

The readiness gate no longer accepts `pg_isready` alone. It validates the bounded
container name, waits until `/proc/1/comm` is exactly `postgres`—proving the
entrypoint has execed the final PID 1—and then requires a no-password `SELECT 1`
with `ON_ERROR_STOP` before role preparation or restore. Both probes retry inside
the existing 60-second deadline. A timeout still fails closed and includes only the
existing bounded private container-log tail; checksum, decompression, SQL, ownership
and invariant failures are never retried or reclassified as startup races.

The top STRIDE risks are denial of service against recovery assurance and alert
attention through a false failed-state, repudiation when a coarse readiness probe
misstates which PostgreSQL instance was ready, and tampering risk if repeated false
positives train an operator to dismiss a genuine restore-integrity failure. The
direct blast radius was one networkless, volume-free disposable container and the
private restore success marker. No live database connection, production write,
learner record, credential disclosure or public diagnostic detail occurred; the
public surface exposed only the existing three-field generic degraded status.

Local service failure was synchronous, but the first GitHub alert run began 3 hours
49 minutes later. Although the workflow requests runs twice hourly, observed gaps
exceeded four hours: GitHub scheduled workflows can be delayed or dropped. This
incident therefore supersedes earlier hard external-MTTD claims. Local hourly health
remains the bounded machine signal; guaranteed external and human MTTD are unbounded
until an independently scheduled monitor and acknowledged notification path exist.

The incident runbook now distinguishes the narrow startup signature from checksum,
restore and invariant failures; preserves journals/image/ownership evidence; permits
one reviewed networkless rerun; and requires full restore, health and external-smoke
recovery before closure. The tabletop must cover the temporary-to-final server
transition, a final PID 1 that never becomes `postgres`, a SQL probe timeout and a
real corrupted dump that must not be normalized as readiness noise.

No vendor, credential, subprocessor, DPA or personal-data flow is added. GitHub's
existing best-effort schedule is now documented honestly; no vendor MTTD guarantee
is inferred. If a future restore incident involves personal data exposure, the
applicable GDPR Article 33 72-hour assessment remains mandatory. FAIR/ALE cannot be
defended without downtime, alert-fatigue, response-cost and incident-frequency
inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full tests, a real
networkless restore, healthy local publication, full CI and exact-SHA external
smoke.

### Bounded pre-deploy database-backup retention — 2026-10-18

The root deployment-backup directory contained 36 `.sql.gz` files. Twenty-one
matched the exact current pre-deploy contract; 15 legacy or explicitly named
intervention/role backups plus the separate checksummed `daily/` tree were outside
scope. The current exact set totaled 1,218,636 bytes and grew on every backend
deployment without a success-file retention bound.

The deployment now validates retention immediately after publishing a fresh verified
dump and before backend build, migration or cutover. It retains the newest 10 exact
`pcep_db_<UTC-basic>.sql.gz` files. Matching candidates must be owned by the invoking
user, private regular files, not future-dated, fully gzip-readable and contain the
PostgreSQL dump header. Removal reopens and rehashes the exact candidate, compares
device, inode, size, modification time and SHA-256 with the reviewed record, deletes
oldest first and durably flushes the parent after each unlink. Any unsafe match or
validation failure aborts before a live-service change. A standalone dry-run/apply
path uses the same `backend-maintenance` lock and never traverses subdirectories or
uses globs. The 10-file floor covers twice the five-image application rollback
window; the independent checksummed daily policy retains 30 recovery points.

The top STRIDE risks are tampering/path substitution that redirects a destructive
unlink, denial of service when a corrupt or attacker-created exact match blocks a
release, and repudiation when a broad age-based cleanup cannot prove which recovery
artifacts it removed. Exact path containment, owner/mode/type checks, no-follow open,
content and identity revalidation, a narrow filename allowlist, oldest-first durable
unlink and fail-closed locking address those risks. This does not pretend that a
malicious process already running as the backup-owning UID is a separate security
boundary; suspected owner compromise remains a host incident.

The reviewed live plan selects 11 oldest exact files totaling 635,917 bytes and
retains 10 exact files totaling 582,719 bytes. Its maximum authorized deletion blast
radius in this run is those 11 named files only. It cannot select the 15 legacy or
named dumps, `daily/`, configuration/frontend artifacts, the live database or a
running container. The current database remains the reconstructible question bank,
not learner-account data.

Future accumulation or retention failure is detected synchronously on the next
backend deployment, before build/cutover; with no deployment, no new pre-deploy dump
is created and the set cannot grow through this path. Operator-visible MTTD is the
command runtime, while guaranteed acknowledgement remains unbounded. Response must
preserve the plan and filesystem evidence, verify the daily checksum plus isolated
restore, and forbid wildcard cleanup. The tabletop now covers a replaced inode
between plan/apply, corrupt exact gzip, future timestamp, concurrent deployment and
power loss or directory-`fsync` failure after a partial oldest-first apply.

No vendor, credential, subprocessor, DPA or data flow is added. If future backups
contain personal data and retention handling exposes or destroys it outside policy,
the GDPR Article 33 72-hour assessment remains mandatory. FAIR/ALE cannot be
defended without recovery-value, storage-failure, deployment-frequency, response-
cost and downtime inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused
and full tests, reviewed live dry-run, green CI, applied exact-path inventory,
successful isolated restore and exact-SHA external smoke.

### Finalized frontend snapshot health inventory — 2026-10-19

The reviewed retention preview found eight exact finalized frontend rollback roots
and eight matching external copies. Six exact paths—three in each location—were
removed only through the reviewed retention utility, reclaiming about 98.7 MiB; no
legacy tree, live release, database artifact or unrelated host image was selected.
The post-cleanup inventory contains five rollback roots and five backup copies. Each
location currently accounts for exactly 73,003,008 allocated bytes (about 69.6 MiB).

Operations health now walks those two finalized inventories read-only every hour.
It accepts only the exact current names, real owner-controlled parent directories,
owned regular files/directories and no world-writable entries. Malformed reserved-
prefix names, symlinks, special files, more than 10 snapshots or more than 512 MiB
allocated in either location publish the existing three-field generic `degraded`
marker and a bounded private diagnosis. The detector does not validate release
contents, acquire deletion authority or replace the existing explicit preview/apply
retention path.

The top STRIDE risks are denial of service from silent disk growth, tampering through
a symlink/special or reserved-prefix impostor, and repudiation when operators cannot
reconstruct which finalized set existed at detection time. The maximum direct blast
radius in the reviewed live state is a read-only metadata walk of 10 trees totaling
146,006,016 allocated bytes across the two locations, plus replacement of one
three-field health marker. The configured guardrails degrade at 11 trees or more than
512 MiB per location. The control cannot delete or alter a snapshot, live frontend,
database, container, legacy release or unrelated backup. A process already running
as `micu` remains inside the same host-control boundary and can forge this local
signal.

Threshold crossing becomes machine-visible on the next hourly health run. GitHub's
external schedule is best effort and observed delays have exceeded four hours, while
delivery to and acknowledgement by a named human remain unverified; guaranteed
external and human MTTD are therefore unbounded. Response preserves journals and
metadata, previews exact retention, validates live plus retained releases, forbids
wildcards and closes only after healthy local publication and public smoke. The
tabletop must cover count growth, oversized allocation, malformed prefix, symlink or
special entry, a concurrent retention disappearance and an unexplained owner/mode
change.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If future
snapshot handling exposes personal data, the GDPR Article 33 72-hour assessment is
still mandatory. FAIR/ALE cannot be defended without release frequency, disk-loss,
downtime, response-cost and incident-frequency inputs. The CISO verdict is **SHIP
WITH GUARDRAILS** after focused/full tests, exact unit installation, healthy live
publication, green CI and exact-SHA external smoke.

### Deploy-time backend rollback-image bound — 2026-10-19

Backend deployment created one exact timestamped rollback tag on every attempt, but
its five-image retention was a separate manual operation. The reviewed live dry-run
is healthy at exactly five valid tags and selects zero removals today. Without an
automatic gate, the next successful or interrupted deploy would recreate silent
host-disk growth and make detection depend on a later operator preview.

Deployment now applies the existing exact repository, metadata, secret-name,
container-use and immutable-ID controls immediately after tagging the verified live
image, while it still owns `backend-maintenance`. It retains five valid rollback
images and permits only the normal one-in/one-out removal of one oldest unused tag.
Any invalid tag is preserved as evidence; an inventory needing two or more removals,
a tag/ID change or new container use fails closed before database backup, candidate
build, migration or service cutover. Candidate/review repositories, PostgreSQL,
build cache and every other host application remain outside the allowlist.

The top STRIDE risks are denial of service through unbounded image accumulation,
tampering through tag replacement between review and removal, and repudiation when
an automatic cleanup cannot prove which immutable image it selected. The maximum
destructive blast radius per deploy is exactly one allowlisted rollback tag and the
unshared layers Docker associates with that one unused image ID; five newer verified
tags, all container-used images and all other repositories remain protected. In the
current live state this is a zero-removal plan across five valid rollback IDs. The
control creates no network path and reads no database, credential or learner data.

Inventory or validation failure is synchronous in the invoking deploy and precedes
backup/build/cutover, so machine and invoking-operator MTTD are immediate. Guaranteed
human acknowledgement outside that terminal remains unbounded. Response preserves
Docker events and exact tag/ID/container evidence, forbids global prune/force,
previews manual retention, scans and tests retained IDs, and retries only from a
one-removal-or-smaller clean state. The tabletop must cover an invalid newest tag,
tag replacement after plan, a container starting between plan/apply, two excess tags
after interrupted attempts and a Docker removal failure.

No vendor, credential, subprocessor, DPA or personal-data flow is added. If a wider
host compromise exposes personal data, the GDPR Article 33 72-hour assessment remains
mandatory. FAIR/ALE cannot be defended without deployment frequency, unique-layer
growth, downtime, response-cost and incident-frequency inputs. The CISO verdict is
**SHIP WITH GUARDRAILS** after focused/full tests, a healthy live dry-run, green CI
and exact-SHA external smoke.

### End-to-end daily-backup success attestation — 2026-10-19

A complete, checksum-valid dump previously proved only that the first part of the
daily job succeeded. If retention, its final inventory or later durable bookkeeping
failed after dump publication, backup freshness could still appear healthy. The
failed systemd state supplied a separate hourly signal, but that state is volatile
across an explicit reset and is not the durable end-to-end record of the job.

The backup service now owns a private mode-0700 systemd state directory and
atomically writes one mode-0600, two-field success marker only after dump durability,
checksum publication, verification of every retained pair, bounded retention and a
second complete inventory all succeed. Pre-replacement failure durably removes the
random temporary and preserves the prior marker. Operations health reads this state
through one read-only path and requires both the newest verified dump and the last
complete-job marker to be no more than 26 hours old. Public output remains the same
three generic fields and contains no path, digest, count or failure detail.

The top STRIDE risks are repudiation through a partial job being mistaken for full
success, denial of service against recovery assurance through repeated late-stage
failure, and tampering with a forged or unsafe marker. The direct data blast radius
is one private JSON file smaller than the existing 256-byte reader ceiling and one
daily backup run; this change adds no database write, remote operation or deletion.
Existing retention remains bounded to complete pairs beyond the newest 30, and a
marker failure does not expand that allowlist. A process already controlling
`micu`/Docker can forge this same-host signal and remains a host-compromise boundary.

A failed oneshot is machine-visible immediately in systemd and on the next hourly
health invocation. Independently, a last-success marker older than 26 hours becomes
degraded on the next hourly run, so marker-based detection is bounded to roughly 27
hours after the last complete success. GitHub's requested external schedule can be
delayed or dropped, and verified human delivery/acknowledgement is still absent, so
guaranteed external and human MTTD remain unbounded. Response preserves both
journals, marker/dump metadata and storage events, verifies all complete pairs,
forbids hand-written markers and requires one successful backup plus isolated restore
before closure. The tabletop must cover a dump that succeeds before retention fails,
a checksum-unlink or directory-`fsync` failure, marker temporary-write/replace/flush
failure, a stale prior marker and a reset failed-unit state.

No vendor, credential, subprocessor, DPA, personal-data flow or retention period is
added. If a wider incident risks personal-data confidentiality, integrity or
availability, the applicable GDPR Article 33 72-hour assessment remains mandatory.
FAIR/ALE cannot be defended without backup value, failure frequency, outage,
response-cost and loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after
failure-injection/full tests, exact unit installation, one real successful backup,
healthy local publication, green CI and exact-SHA external smoke.

### Durable analytics-retention success attestation — 2026-10-19

The PCEP-scoped Umami retention transaction already matched one canonical website
UUID and domain, bounded its statements and lock waits, and rolled previews back.
Its only recurring detection evidence, however, was the systemd failed state. An
explicit reset or reboot could erase that state without proving that the published
180-day policy had been applied successfully.

An applied run now atomically publishes a base-mode-0600 two-field success marker
only after the database transaction commits. A dry-run is structurally refused
marker publication. The dedicated `umami` account owns both marker and base-
mode-0700 state directory; two post-success ACLs give `micu` only directory traversal
and marker read, without exposing the Umami environment or granting a write. Because
POSIX ACL masks appear in group mode bits, operations health requires the effective
0710/0640 modes and the complete numeric ACL sets: `umami` owner, one named `micu`
entry, empty owning-group and `other` permissions, and no extra entry. It also checks
the schema and 26-hour age through a read-only mount. The daily timer moves from
02:47 to 02:17 plus at most 15 minutes of jitter, leaving the normal 02:47 health
invocation outside the publication window.

The top STRIDE risks are repudiation when a preview or reset failed state is mistaken
for applied retention, information disclosure if monitoring gains access to Umami
credentials or rows, and denial of service/compliance failure if expired data remains
indefinitely. The destructive blast radius is unchanged: only expired rows for the
single configured PCEP website across the six allowlisted table operations inside
one transaction. The new write radius is one private JSON file below 256 bytes plus
two named read/traverse ACLs. It adds no table, website, credential, remote endpoint
or broader database privilege.

Transaction, marker or ACL failure is synchronous in the oneshot and visible through
its failed state. Independently, the prior marker becomes unhealthy after 26 hours
and the next hourly run gives a marker-based upper bound of roughly 27 hours from the
last committed success. GitHub schedule and human acknowledgement remain unbounded.
Response preserves private journals/ACLs, previews the exact scoped transaction,
forbids hand-written markers and broad SQL, and closes only after an applied rerun
and healthy public contract. The tabletop must cover database timeout/rollback,
commit followed by marker failure, preview marker refusal, wrong owner/mode, ACL
failure, stale prior success and a reset systemd failed state.

No new vendor, subprocessor, DPA, credential or personal-data category is added;
this control enforces the already published self-hosted Umami retention period. A
breach involving analytics identifiers or events still requires the applicable GDPR
Article 33 72-hour assessment. FAIR/ALE cannot be defended without retained-row
volume, violation duration, response-cost, regulatory and incident-frequency inputs.
The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full tests, exact unit
installation, one real applied retention run, healthy local publication, green CI
and exact-SHA external smoke.

### Host patch/reboot recovery proof — 2026-10-19

The shared host was running kernel `7.0.0-29-generic` while the trusted installed
same-flavour inventory already contained `7.0.0-38-generic`, and
`/var/run/reboot-required` named kernel and libc updates. `needrestart` also reported
Docker among the services using superseded components. A reboot is host-wide and
can affect unrelated projects, so neither repository automation nor a PCEP agent is
authorized to perform package installation, service restarts or the reboot without
a reviewed co-tenant window and recovery-console access.

The new two-phase proof is read-only against production. Preflight requires clean,
exact `main`; exact installed Nginx/systemd/runtime policy; healthy Nginx, Docker and
Cloudflared; six quiescent non-failed PCEP oneshots; and the complete external
production contract. It derives the newest installed kernel only from root-owned,
non-writable, real `/boot/vmlinuz-*` files matching the running kernel flavour. It
then atomically creates one caller-selected, non-existing mode-`0600` JSON evidence
file in an owner-controlled non-writable-by-peers directory. Postflight accepts only
that bounded schema and proves a changed kernel boot ID, the exact expected kernel,
the same reviewed commit, cleared reboot-required state and every live check before
atomically marking the record complete.

The top STRIDE risks are denial of service when Nginx, Cloudflared, Docker or the
database does not recover; repudiation when an operator assumes that a reboot or
new kernel happened without durable proof; and tampering through a replaced state
file, unsafe kernel candidate or drifted installation. A compromised `micu` or root
identity remains able to forge same-host evidence. The checker itself writes one
private JSON file below 4 KiB and performs no package, service, timer, container,
database or public-data mutation. The maintenance event can temporarily affect all
active PCEP learners and every same-host project; PCEP learner progress remains in
the browser and the 308-question bank remains reconstructible.

Gate failures are synchronous, so operator MTTD during the window is immediate.
The twice-hourly external workflow and hourly local publisher remain recovery
signals afterward, but scheduled GitHub execution and human acknowledgement have no
guaranteed upper bound. Response preserves the evidence and relevant journals,
uses provider-console kernel rollback when boot fails, changes only an identified
failed dependency and repeats postflight. The tabletop scenarios are unchanged boot
ID, old-kernel boot, Docker recovery failure, a timer/oneshot race, replaced or
permissive evidence and a healthy homepage with degraded operations state.

No vendor, credential, subprocessor, DPA or personal-data category is added. If a
wider maintenance incident risks personal-data confidentiality, integrity or
availability, the applicable GDPR Article 33 72-hour assessment remains mandatory.
FAIR/ALE is not defensible without outage frequency, co-tenant impact and business-
loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full tests,
one live preflight dry proof without reboot, full CI and exact-SHA external smoke.

### Pinned Trivy scanner refresh — 2026-10-20

The repository's secret and container-image scanner moved from Trivy `0.75.0` to
the official `0.76.0` multi-architecture OCI index at the reviewed immutable digest
`sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222`.
The upstream release declares no breaking change and includes scanner hardening and
additional cryptographic analysis. All three executable defaults use the same
tag-and-digest pair so a caller cannot silently receive different scanner bytes by
choosing a different Make target.

The relevant STRIDE risks are supplier tampering of the scanner, repudiation from
inconsistent pins and denial of service from a scanner regression. Digest binding,
GitHub Actions SHA pinning and clean secret/image/misconfiguration scans limit those
risks; a compromised upstream image at that reviewed digest could still affect the
ephemeral scanner container and its read-only repository view. It cannot write the
worktree, production data or images being inspected. A failed scan is synchronous
in CI and local validation, so machine MTTD is immediate; human acknowledgement
still depends on the existing GitHub notification gate. Response is to preserve the
failed run, compare the upstream release and registry manifest, revert all three
pins atomically and repeat the scans.

No hosted vendor, credential, subprocessor, DPA or personal-data flow is added.
The existing Aqua Security/GHCR supply-chain dependency is refreshed rather than
expanded. A broader incident involving personal data retains the GDPR Article 33
72-hour assessment requirement. FAIR/ALE remains indefensible without incident
frequency and business-loss inputs. The CISO verdict for this bounded tool refresh
is **SHIP** after scanner regression checks and full CI.

### Container base-image update monitoring — 2026-10-20

Dependabot now proposes weekly updates for the pinned backend, PostgreSQL and
frontend Dockerfiles in addition to Actions, npm and pip. It cannot
merge any proposal. Major image changes remain excluded from routine updates, the
seven-day cooldown applies to ordinary releases, and every resulting pull request
must pass the existing required CI and dependency-review controls. Regression tests
also bind the Python and Node image versions to every CI toolchain declaration and
the PostgreSQL base digest to the CI service, causing an incomplete automated edit
to fail closed.

The top STRIDE risks are supplier tampering in a refreshed base image, denial of
service from an incompatible image and repudiation when coupled runtime/CI pins
drift. Immutable digests, explicit version tags, mandatory rebuilds, Trivy scans and
protected-branch CI limit these risks. A malicious accepted base could affect the
backend database/question-bank availability or the ephemeral frontend build output;
Dependabot itself receives repository metadata and can only propose a branch, not
access production or merge. Detection occurs on the weekly proposal and synchrony
failures are immediate in CI. Response closes or reverts the proposal, preserves
scan/build evidence and retains the last reviewed runtime image for rollback. The
existing image rollback drills cover runtime failure; the general human tabletop
remains outstanding.

GitHub/Dependabot and the existing official-image registries are already in scope;
no vendor, credential, subprocessor, DPA or personal-data flow is added. A broader
incident involving personal data retains the GDPR Article 33 72-hour assessment.
FAIR/ALE remains indefensible without incident frequency and business-loss inputs.
The CISO verdict is **SHIP WITH GUARDRAILS** after configuration validation, full CI
and exact-SHA external smoke.

### Pinned zizmor workflow scanner refresh — 2026-10-20

The offline GitHub Actions security scanner moved from `zizmor` 1.30.1 to the
upstream 1.31.1 Linux x86_64 release. The archive remains bound to the SHA-256
published with that release (`d185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99`)
before extraction. Version 1.31.1 fixes a 1.31.0 regression in the
`dangerous-triggers` audit; the repository had not adopted the affected 1.31.0
release. The scanner still runs without credentials, configuration or repository
ignore rules, in strict-collection, pedantic and offline modes.

The top STRIDE risks are supplier tampering with the downloaded scanner, denial of
service from a scanner regression and repudiation if a workflow finding could be
silently ignored. The release digest, fail-closed checksum, credential stripping,
disabled ignores and required CI gate constrain these risks. Blast radius is the
ephemeral CI/local scan and its read-only repository inputs; the scanner has no
production or customer-data access. Checksum and audit failures are synchronous, so
machine MTTD is immediate. Response preserves the failed run and archive metadata,
reverts the two scanner constants together and repeats the offline audit; the
dangerous-trigger scenario belongs in the next general CI-compromise tabletop.

The existing GitHub/upstream supply-chain dependency is refreshed, not expanded;
no vendor, credential, subprocessor, DPA or personal-data flow is added. A broader
incident involving personal data retains the GDPR Article 33 72-hour assessment.
FAIR/ALE remains indefensible without incident frequency and business-loss inputs.
The CISO verdict is **SHIP** after checksum verification, the pedantic offline audit,
the full test suite and exact-SHA external smoke.

### PostgreSQL image-monitoring correction — 2026-10-20

The first hosted `docker-compose` Dependabot run failed because it interpreted the
locally built `pcep_webapp-postgres` image name as a private Docker Hub repository.
It could not see the actual upstream PostgreSQL source supplied only through a
Compose build argument. The ineffective Compose updater was removed. The immutable
PostgreSQL source is now a direct `FROM` instruction, `/docker/postgres` is covered
by the working Docker updater, and regression/runtime checks bind that Dockerfile,
its OCI provenance label and the CI database service to the same reviewed digest.
The hosted failure was preserved as run `39372944027`; no credential was added to
mask a public/local image-modeling error.

The top STRIDE risks are spoofing a local image as a remote registry dependency,
supplier tampering with the real PostgreSQL base and denial of service from silent
monitoring failure. Direct immutable provenance, a weekly proposal, fail-closed
synchrony tests and mandatory image scanning constrain them. Blast radius remains
the database image and its availability; Dependabot has repository metadata but no
production or database access. A hosted update failure is visible on each config
change or weekly run, while digest drift fails synchronously in CI. Response keeps
the failing run, rejects registry credentials for local-only names, reverts the
proposal if needed and rebuilds/scans the last reviewed digest. The next general
supply-chain tabletop should include a red update job with otherwise green CI.

No vendor, credential, subprocessor, DPA or personal-data flow is added. A broader
incident involving personal data retains the GDPR Article 33 72-hour assessment.
FAIR/ALE remains indefensible without incident frequency and business-loss inputs.
The CISO verdict is **SHIP WITH GUARDRAILS** after a clean hosted Docker updater run,
full CI, database-image scanning and exact-SHA external smoke.

### Python and Node image-monitoring correction — 2026-10-20

Hosted Docker updater run `39373789866` proved the PostgreSQL correction but also
showed empty dependency snapshots for `/backend` and `/frontend`. Their immutable
Python and Node references were hidden behind Docker build arguments, which the
updater's direct `FROM` parser does not expand. Both Dockerfiles now use direct,
digest-pinned `FROM` instructions; the backend repeats the identical reference in
its dependency and runtime stages. Regression tests require those instructions to
remain direct, mutually identical and version-synchronized with every CI toolchain.

This closes the silent-detection variant of the prior spoofing/repudiation risk:
a green scheduler run must enumerate all three intended suppliers rather than only
exit successfully. Blast radius, response, vendor/DPA scope and the GDPR 72-hour
assessment remain as documented above. Machine MTTD is weekly for an upstream image
change and immediate in CI for pin drift; guaranteed human acknowledgement remains
dependent on GitHub notification delivery. FAIR/ALE is still unavailable without
frequency and business-loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS**
only after a hosted dependency snapshot explicitly includes Python, PostgreSQL and
Node, full CI passes and exact-SHA external smoke succeeds.

### Python interpreter-line update policy — 2026-10-20

Hosted Docker monitoring correctly opened PR `#121` for `python:3.14.8-slim`, but
Dependabot's SemVer model classified the Python 3.12 to 3.14 language migration as
a routine minor update. Required CI rejected it: the runtime/CI synchrony test
detected that the workflows remained on 3.12.14, and the rebuilt image scan found
four fixable HIGH findings in bundled `msgpack`, `setuptools` and `urllib3`. The PR
was closed rather than weakening either gate. Docker version updates now ignore
minor changes for the `python` dependency while retaining patch and digest updates
on the reviewed 3.12 line. A future interpreter minor requires a dedicated migration
covering CI, hashed dependencies, application compatibility and image findings.

The top STRIDE risks are supplier tampering through an unsafe base refresh, denial
of service or incompatibility from an unplanned interpreter jump, and repudiation
if an automated green label is mistaken for compatibility evidence. Worst-case
blast radius is the backend service and all active learners; the question bank is
reconstructible and this policy change itself has no production, database or
customer-data write path. Drift and fixable image findings fail synchronously in
required CI, giving immediate machine MTTD; upstream patch discovery remains weekly,
while human acknowledgement still depends on GitHub notification delivery.

Response is to preserve and close the failed proposal, retain the last reviewed
image, triage scanner findings and perform any interpreter migration on a dedicated
branch with explicit rollback. The next supply-chain tabletop should inject both an
apparently routine language-line jump and a candidate image with newly fixable HIGH
findings. No new vendor, credential, subprocessor, DPA or personal-data flow is
added. A wider incident affecting personal-data confidentiality, integrity or
availability retains the GDPR Article 33 72-hour assessment requirement. FAIR/ALE
cannot be defended without user volume, outage, response-cost, loss and frequency
inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after focused/full tests, green
required CI, a clean hosted Docker updater run and exact-SHA external smoke.

### Python 3.12.15 runtime patch — 2026-10-20

After the interpreter-line policy reached `main`, hosted Docker updater run
`39451619778` enumerated Python, PostgreSQL and Node and selected only the eligible
Python patch from 3.12.14 to 3.12.15. Its PR `#123` updated the two direct,
digest-pinned `FROM` instructions. Required CI failed closed only because the three
Python workflow toolchains intentionally remained on 3.12.14; 551 other backend
tests passed. The Ops job successfully built and scanned the 3.12.15 candidate.
The controlled replacement updates the two image references and all three CI pins
together while preserving hashed application dependencies and the 3.12 language
compatibility boundary.

The top STRIDE risks are supplier tampering in the refreshed official image, denial
of service from a patch regression and repudiation through runtime/CI version drift.
The immutable multi-architecture digest, fail-closed synchrony test, complete suite
and fixable-HIGH/CRITICAL image scan constrain them. Worst-case blast radius is the
backend service and all active learners; this source change has no direct production,
database or customer-data write path. Pin drift and image findings fail immediately
in required CI, while the weekly updater provides patch-discovery MTTD subject to
GitHub scheduling and human notification delivery.

Response preserves the failed bot proposal and candidate scan, retains the prior
reviewed image for rollback, and reverts all five coupled runtime pins together if
post-merge validation fails. The next supply-chain tabletop should cover a clean
patch that fails application behavior after passing vulnerability scanning. No new
vendor, credential, subprocessor, DPA or personal-data flow is added. A wider
incident affecting personal-data confidentiality, integrity or availability keeps
the GDPR Article 33 72-hour assessment requirement. FAIR/ALE cannot be defended
without user volume, outage, response-cost, loss and frequency inputs. The CISO
verdict is **SHIP WITH GUARDRAILS** after full CI, image scanning, local production
checks and exact-SHA external smoke.

### Redirect credential-stripping advisories — 2026-10-20

The full frontend audit detected HIGH advisories `GHSA-q3jh-wrc6-jgq8` and
`GHSA-8r9p-f939-6h3c` in transitive `follow-redirects 1.16.0`. Axios permits the
patched `1.16.1`, so only the npm lock changed. A clean install selected the patched
artifact, registry signature/attestation verification passed, the full static build
passed and the generated browser bundle contains no `follow-redirects` code.

The top STRIDE risks are information disclosure of authorization or cookie headers
across an attacker-controlled redirect, spoofing of the redirect destination and
tampering with authenticated requests. The vulnerable library is the Node adapter
behind frontend Axios, while production serves static browser assets and excludes
that adapter; practical blast radius is therefore developer/CI Node execution, not
learner browser sessions or the backend/database. Required `npm audit` detected the
advisory on the first full audit after the database update, giving same-run machine
MTTD; human acknowledgement still depends on GitHub notification delivery.

Response preserves the failed report, updates only the transitive lock entry, uses
a clean install and repeats signature, attestation, test and build validation. The
next supply-chain tabletop should exercise a malicious cross-origin redirect from a
Node-side build or audit helper and identify any credential that would require
rotation. No vendor, subprocessor, DPA or personal-data flow changes. Evidence of
personal-data exposure would retain the GDPR Article 33 72-hour assessment. FAIR/ALE
cannot be defended without execution frequency, credential value, response-cost and
loss inputs. The CISO verdict is **SHIP WITH GUARDRAILS** after clean dependency/full
CI audits and exact-SHA external smoke.

## 15. Breaking changes

None.
