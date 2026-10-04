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
      ├─ /static/ and /media/ → host release directories
      ├─ /api/ and /admin/ → 127.0.0.1:8001
      │                         → pcep_backend (Gunicorn, three workers)
      │                         → pcep_db (PostgreSQL 16)
      └─ exact /u/ collection routes → loopback Umami service
```

Cloudflared and Nginx are shared with other applications. The tunnel has a
specific route for another hostname and a catch-all loopback TLS origin. Its
local origin certificate is not verified. UFW exposes SSH and the unrelated
TURN service, but not ports 80/443. Nginx listens on 80/443 for the local tunnel;
the default TLS vhost redirects unknown hosts to `https://micutu.com/`.
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

The CSP keeps `wasm-unsafe-eval`, which Pyodide needs, and does not grant
`unsafe-eval` or `unsafe-inline`. API responses use `default-src 'none'`.
Workbox never stores API, answer, admin, study-page or analytics responses.
Browser progress import is schema-, type-, size- and count-bounded and never
contains an answer key.

Remaining security work:

- The admin login remains Internet-reachable behind Nginx rate limiting and
  Django authentication. Cloudflare Access and enforced operator MFA would
  reduce credential-attack exposure, but require account/dashboard changes that
  were not available locally.
- Cloudflare currently injects a dynamic inline JavaScript-detection challenge.
  CSP blocks it, producing a console warning while leaving the application
  functional. Disable that edge feature rather than weaken CSP.
- The shared tunnel catch-all and `noTLSVerify` increase the impact of a host
  routing error. UFW, the origin guard and strict PCEP host handling contain the
  current exposure, but an explicit PCEP ingress rule with verified origin TLS
  would be clearer.
- Model/admin/seed validation protects normal writes, but a direct ORM or SQL
  write can still bypass the one-correct-choice invariant. A deferred database
  design could encode stronger constraints, though cross-row “exactly one” is
  not a simple check constraint.
- DRF's memory throttle remains per process. The shared Nginx limit closes the
  production gap, but deployments that bypass Nginx must supply a shared cache.
- A full Trivy 0.74.0 scan reports 44 HIGH package occurrences across eight
  unique Debian 13 CVEs. None has a vendor-fixed version, none affects an
  installed Python package and there are zero CRITICAL findings. The current
  non-root, read-only, capability-free runtime limits exposure. Debian 12
  Bookworm was evaluated and rejected because the equivalent base reported 55
  HIGH and five CRITICAL findings, also without vendor fixes. CI blocks new
  fixable HIGH/CRITICAL findings; the unfixed set still requires periodic review.

No secrets were added to Git. The production `.env` remains mode 0600 and was
not printed or copied. No database or Docker volume was deleted.

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

The question-bank snapshot is now normalized before it reaches the setup UI.
Module, difficulty and objective totals must agree with both coverage matrices
and the four module summaries, so a partial or malformed API response produces a
recoverable error instead of crashing the workspace or clamping a quiz against
bad counts. A visible retry cancels any older stats request and preserves the
learner's setup choices.

The Pyodide manager bounds startup at 30 seconds, a run at eight seconds, source
at 20,000 characters, output at 10,000 characters and active/queued jobs at
four. Timeout or fatal failure replaces the worker. The pinned 0.29.4 npm
tarball is verified by SHA-512 before staged extraction. These are browser
resource controls, not a hostile-code sandbox.

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
minimal. Pyodide remains lazy and same-origin. Hashed frontend/admin assets are
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
  headers, JSON request IDs/timing logs without IP/query/cookie/auth data, body
  and rate limits, compression, strict route caching, correct manifest/WASM/JS
  media types and missing-asset 404s. Every reload followed `nginx -t`.
- **Release retention:** a read-only-by-default utility reports only exact
  frontend/static rollback and backup snapshots, enforces at least two retained
  copies and requires `--apply` before removal. Database/security backups cannot
  match its allowlist. No production snapshot was deleted during this work.
- **Cloudflare/Tunnel:** service is enabled and healthy. Live cache behavior is
  BYPASS/DYNAMIC for shell/API/workers and immutable for hashed assets. No
  dashboard setting was changed because no Cloudflare account connector was
  available.
- **Docker:** backend runs as `appuser`, read-only, capability-free, bounded to
  512 MB/128 PIDs with a noexec 64 MB tmpfs and graceful stop. It exposes only
  loopback port 8001. Successful internal readiness probes are omitted from the
  access log only when their marker and loopback peer both match; failures and
  public probes remain logged. The pinned Python base receives current Debian
  security updates during the runtime build. PostgreSQL exposes no host port and
  keeps its named volume.
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
reports zero vulnerabilities. Axios remains exactly at audited 1.18.0 because
1.20.0 alone increased the entry bundle by about 5.9 KB / 1.9 KB gzip with no
security finding to resolve. The validated entry remains 277.89 KB / 88.61 KB
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

No commit was pushed by the engineering assistant, and no authorship, co-author or
generated-by attribution was added.

## 13. Remaining opportunities

1. Protect `/admin/` with Cloudflare Access and operator MFA, after verifying an
   emergency/bypass procedure to avoid lockout.
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
lazy Review chunk return 200, while a deliberately checked expired chunk returns
404. Fresh live Chromium at 390 px loaded the new entry, Dashboard and Exam lazy
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

## 15. Breaking changes

None.
