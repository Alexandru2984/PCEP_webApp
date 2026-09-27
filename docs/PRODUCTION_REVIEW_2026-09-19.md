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
points revalidate. The current main production bundle is approximately 270 KB
JavaScript (86.5 KB gzip) and 46.5 KB CSS (8.4 KB gzip), excluding lazy chunks
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
change or Nginx reload.

## 15. Breaking changes

None.
