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
  moderate/high findings. Django is now 5.2.17 LTS, DRF is 3.17.2, and both
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

No secrets were added to Git. The production `.env` remains mode 0600 and was
not printed or copied. No database or Docker volume was deleted.

## 4. Backend changes

- Added pure `/api/live/` liveness while retaining DB-backed `/api/health/`
  readiness for container and monitoring compatibility.
- Reduced stats from four aggregate queries to one grouped query and exposed a
  bounded coverage matrix without question or answer data.
- Added strict grade/answer request serializers, deterministic error semantics,
  invalid-key 503 behavior, public `ids` filtering for targeted local drills and
  consistent cache/error middleware.
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

The recovery screen follows that same wall-clock deadline while it remains open,
refreshes after browser suspension, switches expired attempts to a clear grading
action and requires confirmation before deleting the saved attempt.

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

## 9. Performance

The stats endpoint now performs one grouped query. Questions prefetch choices;
no N+1 path was introduced. API payloads are capped and public answer data stays
minimal. Pyodide remains lazy and same-origin. Hashed frontend/admin assets are
compressed and immutable; unversioned shell, worker, manifest and runtime entry
points revalidate. The current main production bundle is approximately 272.6 KB
JavaScript (87.1 KB gzip) and 46.5 KB CSS (8.4 KB gzip), excluding lazy chunks
and the Pyodide runtime.

The release process retains older lazy chunks so tabs open across deployment do
not fail. The service worker cleans old named caches and waits for the user to
reload after an update, avoiding an automatic mid-exam takeover.

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
  loopback port 8001. PostgreSQL exposes no host port and keeps its named volume.
- **systemd:** Nginx, Docker and cloudflared are active. The weekly SEO generator
  remains installed as an existing systemd timer.
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

No commit was pushed and no authorship, co-author or generated-by attribution was
added.

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
4. Add external uptime/error monitoring for liveness, readiness and release
   version, without collecting learner behavior or personal data.
5. Re-evaluate PostgreSQL random ordering only when bank size or measured query
   time makes the current implementation material.

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

The analytics build marker has no runtime deployment requirement because Vite
removes it from `dist/index.html`; the verified output still loads the same
`/u/script.js` with the existing privacy attributes. The external-volume
declaration resolves to the three existing `pcep_webapp_*` volumes and live
container mountpoints. No volume, container or data was recreated for that
configuration change. Fresh installations must create the named volumes once,
as documented in README and the operations runbook.

## 15. Breaking changes

None.
