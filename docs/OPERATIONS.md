# Operations Runbook

This project is deployed as a Dockerized Django API behind system nginx, with a
static Vite build served from `/var/www/pcep/frontend`.

## Daily Checks

```bash
make status
make production-smoke
DJANGO_SETTINGS_MODULE=pcep_project.test_settings backend/.venv/bin/python backend/manage.py audit_questions --fail-on-warnings
```

## First-time volume bootstrap

Compose treats persistent data as externally managed so even
`docker compose down -v` cannot delete it. Create the configured volume names
once before the first start (the commands are idempotent):

```bash
docker volume create pcep_webapp_postgres_data
docker volume create pcep_webapp_static_volume
docker volume create pcep_webapp_media_volume
```

The defaults come from `.env.example`; create the matching names instead when
`PCEP_POSTGRES_VOLUME`, `PCEP_STATIC_VOLUME` or `PCEP_MEDIA_VOLUME` is changed.
Create `.env` from `.env.example` for Django and `.env.db` from `.env.db.example`
for the database container. Both must be mode 0600. `PCEP_APP_DB`,
`PCEP_APP_USER` and `PCEP_APP_PASSWORD` in `.env.db` must match the three
`POSTGRES_*` application values in `.env`; the administrator password must differ.

## Local Verification

```bash
make install
make test
make audit
make django-check
make compose-build
make audit-image
make compose-build-frontend
bash scripts/check_postgres_container.sh
make audit-db-image
```

`make test` runs the local SQLite-backed backend test suite plus the frontend
unit/lint/format/build checks. CI runs the backend suite against PostgreSQL.
The pinned image scans cover the backend's Debian/Python packages and the database's
Alpine packages, and fail on fixable HIGH/CRITICAL findings. Unfixed vendor findings
remain visible in a full Trivy report and are reviewed separately rather than
permanently breaking CI. Each audit resolves the requested image to its immutable
ID, exports that exact image to a private temporary archive, and gives the scanner
only the archive and its cache. Never mount the Docker daemon socket into the
scanner: socket access is equivalent to privileged control of the host. The
PostgreSQL runtime check builds the reviewed image,
starts a disposable cluster with the production restrictions, writes data, verifies
the kernel controls and read-only root, restarts it and verifies persistence.
The runtime base pins both Python 3.12.14 and the official multi-architecture
image digest. The runtime stage applies current Debian updates so a versioned
upstream image cannot leave newly fixed packages behind between image rebuilds.
Update the Python version and digest together only after rebuilding, scanning and
running the backend suite. Test code, pytest configuration and development
requirements are excluded from the production build context. Production and
development Python installs use committed transitive locks with SHA-256 hashes;
the Docker build verifies the production lock once while collecting wheels and
again during its network-free runtime install. After intentionally changing an
input requirement, install the development lock and run `make lock-backend`, then
review both lock diffs and repeat the audit and image build.

`make audit-secrets` creates a mode-0700 temporary tree containing only paths known
to Git plus a text rendering of all reachable commit history. It deliberately
excludes ignored/untracked operator files such as `.env`, rclone configuration,
backup data and `.claude/`. The digest-pinned Trivy secret scanner runs against that
tree without network access, capabilities or a writable root filesystem. Repository
`trivy.yaml`, ignore files and secret-rule configuration cannot suppress their own
finding: the scanner starts in `/`, outside the read-only target mounted at
`/workspace`, so target files are data rather than scanner configuration. The
command refuses shallow clones; the CI ops checkout therefore fetches full history.
Scanner output redacts matched values. Treat a finding as exposed even if a later
commit removes it, rotate the credential first, then purge history only through a
separately reviewed procedure.

The frontend builder uses a versioned Node 24/Alpine tag plus the official
multi-architecture image digest. Run it through `make compose-build-frontend`;
the target maps the invoking host UID/GID into the disposable container so a
non-root builder can replace `frontend/dist` without leaving root-owned files or
assuming UID 1000. Its home and npm cache remain inside the disposable container.
The pinned runtime is Node 24.21.0 with npm 11.19.0. `.npmrc` blocks all dependency
lifecycle scripts, including on older npm releases that predate `allowScripts`.
`frontend/scripts/install-dependencies.sh` performs `npm ci --ignore-scripts`, then
checks the lockfile and installed package metadata against an exact reviewed
inventory. Every downloaded dependency artifact must resolve from
`registry.npmjs.org` with SHA-512 integrity; `inBundle` entries must trace to such a
parent artifact. The current graph needs no lifecycle installer. The package
manifest also denies the optional macOS-only `fsevents@2.3.3` installer for npm
versions that understand `allowScripts`. A new version, lifecycle command or
package with an install script fails before any such code runs.
After a dependency change, review both inventory failures before updating the
checker; never replace the script-free install with blanket lifecycle enablement.

`workbox-build@7.4.1` still requests `glob@^11.0.1`. Its resolved 11.1.0 release is
patched for the known CLI injection advisory but is deprecated upstream. Neither
the current Workbox release nor `vite-plugin-pwa@2` changes that dependency. The
frontend therefore applies an exact, scoped override to `glob@13.0.6`. Workbox uses
only the retained `globSync` library API; glob 13 removes the CLI and its associated
dependency subtree. Do not widen the override. On every change, reproduce the PWA
build and offline Playwright test, and remove the override once Workbox declares
support for a current glob major.
CI actions are also pinned to full release commit SHAs. Keep the adjacent
version comments synchronized and review official release notes before updating
those pins; current action majors use the supported Node 24 runtime. Every workflow
uses the explicit Ubuntu 24.04 runner label instead of the moving `ubuntu-latest`
alias. Python jobs pin 3.12.14, matching the backend image and local review
environment. Upgrade either runner or interpreter only as a reviewed change after
the complete CI suite passes on the candidate combination.

Run `make check-workflows` after changing `.github/workflows/`. It downloads the
Linux/amd64 `actionlint` 1.7.12 and `zizmor` 1.30.1 archives over HTTPS, verifies
each release's pinned SHA-256 before extraction, and validates every workflow.
Actionlint checks schema, expressions and embedded shell; zizmor's pedantic offline
persona checks hash pinning, permissions, triggers, secret handling and other static
CI security properties. No GitHub token is exposed to the scanner.

The command supplies trusted tool configuration, disables repository ignore rules,
passes every workflow explicitly, and rejects symlinks, nested entries and unsafe
filenames in the workflow directory. Update each version, archive checksum and this
documentation together after reviewing the upstream release; never replace a fixed
version with `latest`.

`.github/workflows/dependency-audit.yml` installs and audits the committed hashed
Python locks and audits the npm lockfile every day at 04:17 UTC, with manual
dispatch available.
It is independent of repository activity, uses read-only repository permissions,
has ten-minute job limits and runs `npm ci --ignore-scripts` before the Node audit.
This detects advisories published between code changes without granting a scanner
write access or executing dependency lifecycle scripts. Both the push/PR and daily
audits run `npm audit signatures` to verify registry signatures and provenance
attestations for the resolved packages. Reproduce either failure locally with
`make audit` before changing a version pin.

`.github/dependabot.yml` proposes reviewed version updates for GitHub Actions each
Monday and frontend npm dependencies each Tuesday at 05:23 Europe/Bucharest. A
seven-day cooldown applies only to routine version updates; GitHub security updates
are not delayed by that setting. Compatible minor/patch updates are grouped by
ecosystem and npm dependency type, while major upgrades stay isolated. At most
three routine PRs per ecosystem remain open; security PRs are outside that limit.
There is no auto-merge configuration.

The configuration file enables version-update proposals after it reaches the
default branch. Dependabot alerts and security updates remain repository settings;
confirm they are enabled under GitHub's security settings. If enabled, this file's
cooldown and routine PR limit do not delay or count their security-update PRs.

`.github/workflows/dependency-review.yml` compares the dependency snapshots for
every pull request targeting `main` through GitHub's dependency review API. It
fails its check when a change introduces a known vulnerability rated moderate or
higher in runtime, development or unknown scope. The workflow is separate from CI,
uses only `contents: read`, does not post PR comments and pins the official action
to its full release commit.

License enforcement is intentionally disabled: the repository has not adopted a
reviewed allowlist, so a generic scanner default must not stand in for legal policy.
OpenSSF scorecard output is also disabled because it is informational rather than a
merge rule. Revisit both settings only through a documented policy change. This
PR-time comparison complements rather than replaces the full-tree push audit and
the daily advisory audit; it cannot be reproduced offline because the comparison
comes from GitHub's dependency graph. Run `make check-workflows` locally after any
configuration change.

The repository dependency graph and Dependabot alerts were enabled on 2026-10-05.
GitHub's initial SBOM contains 609 packages and 1,150 relationships, with no open
Dependabot alert at activation time. Check the current setting without changing it
with `gh api -i repos/Alexandru2984/PCEP_webApp/vulnerability-alerts`: HTTP 204 means
enabled. Do not disable it; GitHub's disable endpoint removes both alerts and the
dependency graph that this workflow requires. Dependabot security updates remain a
separate, disabled setting and no security-update PR is created automatically.

The hosted dependency review and all four CI jobs are required by `main` branch
protection. Required checks are bound to the GitHub Actions app rather than accepted
from any producer with a matching name. The branch must be current before merge;
pull requests, resolved conversations and linear history are mandatory, including
for repository administrators. Zero approving reviews are required because this is
a single-maintainer repository, while force pushes and branch deletion are blocked.
Inspect the live control without changing it with:

```bash
gh api repos/Alexandru2984/PCEP_webApp/branches/main/protection
```

Do not rename or remove a required workflow job until its replacement has completed
successfully on a pull request and the protection setting has been updated. If an
incident requires a temporary gate change, record the reason and exact prior JSON,
make the narrowest change through repository administration, then restore and
re-verify protection immediately after the incident.

Python is deliberately excluded because its two SHA-256 lock files must be
regenerated together with `make lock-backend`, reviewed and audited. Container base
updates are also kept manual because each tag/digest pair must be rebuilt, runtime
tested and scanned together. The daily advisory workflow still detects vulnerable
Python and npm resolutions between upgrades. `make check-workflows` validates both
the workflows and Dependabot configuration with strict offline zizmor collection.

## Public Production Smoke

```bash
make production-smoke
# Optional for another reviewed deployment:
make production-smoke PRODUCTION_URL=https://pcep.example.com
```

The standard-library-only check makes bounded, retryable GET requests with normal
TLS certificate verification. It verifies the shell, referenced fingerprinted
JS/CSS entry assets, immutable asset caching, service-worker policy, liveness,
database readiness, separate frontend and backend release markers, request IDs,
aggregate question counts,
module/objective/difficulty matrices, security headers and API no-store behavior.
It also requires `/admin/login/` to remain a non-redirecting, cookie-free 404 with
a deny-all CSP, so a vhost regression cannot silently republish Django admin.
It validates strict answer-safe shapes for random, daily, detail and search
responses, then verifies that a three-question targeted drill preserves the
requested order. It never calls an answer, grade or other write endpoint and does
not send learner state, cookies or identifiers.

Successful output reports `frontend_release` from the static shell metadata and
`backend_release` from the API response headers. This makes an incomplete or stale
frontend publication visible even when the backend is healthy.

`.github/workflows/production-smoke.yml` runs this contract every six hours and
on manual dispatch with read-only repository permissions. Its failure appears in
GitHub Actions and the README badge. The push/pull-request CI remains independent
of production availability, so a transient Internet or production outage cannot
block code review.

## Daily Database Backup

`make deploy-backend` always creates a verified pre-deploy dump, but deploy cadence
is not a recovery-point policy. `make backup-database` uses the same atomic dump
implementation to create
`/home/micu/backups/pcep/daily/pcep_db_daily_<UTC>.sql.gz`, plus a private SHA-256
sidecar. It validates the gzip stream and PostgreSQL dump header before publication,
fsyncs the completed files, verifies every retained checksum on each run and only
then removes complete daily pairs beyond the newest 30. Failed dumps never trigger
retention. Unpaired files, pre-deploy dumps, role dumps, configuration backups and
frontend snapshots are outside its exact filename pattern and are never removed.

Install the reviewed timer after creating its only writable directory:

```bash
sudo install -d -m 0700 -o micu -g micu /home/micu/backups/pcep/daily
sudo install -m 0644 ops/systemd/pcep-db-backup.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/pcep-db-backup.timer /etc/systemd/system/
sudo install -m 0644 ops/systemd/pcep-db-restore-check.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/pcep-db-restore-check.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pcep-db-backup.timer
sudo systemctl enable --now pcep-db-restore-check.timer
sudo systemctl start pcep-db-backup.service
sudo systemctl start pcep-db-restore-check.service
systemctl status pcep-db-backup.timer pcep-db-backup.service \
  pcep-db-restore-check.timer pcep-db-restore-check.service
```

The timer runs daily at 01:17 local time with up to 15 minutes of randomized delay
and catches up after downtime. The oneshot runs as `micu`, receives no database
credential file, reaches PostgreSQL only through the existing Docker Unix socket,
and has a read-only host view except for the daily backup directory. Inspect recent
runs with `journalctl -u pcep-db-backup.service` and verify a sidecar from inside the
daily directory with `sha256sum --check <backup>.sha256`.

The restore timer runs each Sunday at 03:17 local time with up to 30 minutes of
randomized delay and catches up after downtime. `make verify-database-restore`
performs the same drill on demand. It verifies the newest private dump and checksum,
uses the exact immutable image ID of the live PostgreSQL container, then restores
into a disposable container with no network, capabilities, writable root or
persistent data volume. The drill uses no production database credential and never
connects to the live database. It verifies the application table owner, migrations,
the one-correct-choice index and every question's four-choice/one-answer invariants,
then verifies the source checksum again and removes the container. Inspect runs with
`journalctl -u pcep-db-restore-check.service`. Repeat the drill directly after
backup-code, PostgreSQL or schema changes; never test a restore over the live
database.

Docker can lose the metadata for an image while a container created from its
layers continues to run. If the exact live ID is no longer runnable, the scheduled
service falls back only to the reviewed `pcep_webapp-postgres:16.15-alpine3.24`
image. The fallback is resolved to an immutable ID and accepted only when it runs
as `postgres`, has the reviewed restore-profile label and entrypoint, embeds no
runtime secret and matches the live server's PostgreSQL major version. Build and
scan that fallback with `bash scripts/check_postgres_container.sh` and
`make audit-db-image` before installing an updated restore unit.

These local logical dumps improve recovery point coverage but remain on the same
physical host; they do not protect against host or disk loss. Replication to
independently controlled storage remains required when an off-host destination and
credentials are available.

## Encrypted Offsite Database Backup

The repository includes a fail-closed rclone upload and round-trip verification
command, but its service and post-backup trigger are intentionally not installed.
Follow [`OFFSITE_BACKUP_RUNBOOK.md`](OFFSITE_BACKUP_RUNBOOK.md) before activation. In
particular, do not use a raw storage remote, the retiring shared Google Drive OAuth
client or a crypt key stored only on this host. The runbook requires a dedicated
crypt remote, provider immutability/versioning, offline recovery material and a
tested independent alert.

The preflight validates both the requested destination and the backend path wrapped
by the crypt remote. It rejects absolute, empty, repeated or traversal segments and
a crypt remote that references itself. This path validation demonstrates safe
structure only; provider-side least privilege and a PCEP-dedicated bucket or prefix
must still be reviewed independently.

The reviewed Cloudflare R2 candidate profile requires a new private bucket created
with EU jurisdiction, a bucket-scoped Object Read & Write token, and a native Bucket
Lock on the physical encrypted prefix. The existing shared raw R2 remote is not
eligible. Standard S3 versioning/Object Lock APIs are not available on R2, and its
provider logs do not replace the independent 24-hour missed-success alert. Exact
evidence requirements and the secret-free rclone configuration shape are in the
runbook.

The preflight enforces that reviewed local shape: exactly two remotes, the Cloudflare
provider, the jurisdiction-specific EU endpoint, static non-ambient credentials,
disabled bucket-creation checks and a `bucket-name/encrypted` backend path. This does
not attest the token scope, bucket jurisdiction, public-access state or Bucket Lock;
those remain provider-side activation evidence.

`make offsite-backup-preflight` performs no upload. `make offsite-backup` is allowed
only for a manually reviewed first run after every activation gate passes. Neither
command deletes or applies retention to remote data. Both require an explicit
PCEP-only rclone config path; they never fall back to the operator's shared config.

Run `make check-systemd` after changing any file under `ops/systemd`. It verifies all
repository-owned services and timers with the host's `systemd-analyze`, loads
adjacent drop-ins and rejects an orphan or unsafe drop-in name. The validator stages
the exact repository tree inside a mode-0700 temporary filesystem root together with
non-executed placeholders for the fixed production interpreter and host-provided
units. This makes validation independent of a developer or CI runner having
`/home/micu/PCEP_webApp` installed while preserving `systemd-analyze`'s executable,
dependency, directive and sandbox checks. Any diagnostic, including a warning that
would otherwise return success, fails the command. Push/pull-request CI runs this
check on Ubuntu 24.04 as well.

## Backend Deploy

```bash
make deploy-backend
```

The deployment command refuses tracked uncommitted changes. Before building, it
verifies the live container, tags its exact image for rollback and streams a
gzip-compressed PostgreSQL dump into a mode-`0600` file. It validates the dump
header and checksum, then builds the candidate with the Git revision, runs
Django deploy checks and refuses pending migrations. It resolves the candidate's
immutable Docker image ID and runs the blocking Trivy audit against that exact
image. A scan or scanner failure leaves the running container untouched. Only
then does it recreate the backend service, wait for the Compose healthcheck,
audit the live question bank read-only and verify readiness plus `X-PCEP-Release`
through the public domain. The rollback tag and dump are printed as soon as they
are safe.

For a reviewed release that intentionally contains migrations, inspect them and
run `make deploy-backend BACKEND_DEPLOY_FLAGS=--allow-migrations`. This records
the plan and lets the existing fail-fast entrypoint apply it. Never use that flag
merely to bypass an unexpected pending migration.

`make compose-build`, `make deploy-backend` and `make deploy-frontend` inject the
current Git revision into their artifacts. Override `RELEASE=<bounded-label>`
only for an intentional release label. Use `make deploy-backend` for production;
running `make compose-build` first can displace the untagged live image before a
rollback snapshot exists. API responses expose the backend revision in
`X-PCEP-Release`; the frontend revision appears in the footer, which makes
partial deploys and stale PWA tabs immediately distinguishable. Responses
generated directly by Nginx (for example, an over-limit request) do not carry
the Django release header.

If an earlier local build already displaced the exact live image metadata,
routine deployment stops before backup or service replacement. Do not recover
with `docker commit`: the committed container configuration can embed runtime
secrets. Select an already retained, reviewed rollback image that is compatible
with the current schema, inspect it, and invoke the explicit recovery path:

```bash
make deploy-backend BACKEND_DEPLOY_FLAGS='--fallback-rollback-image <reviewed-tag>'
```

This path is used only when the exact live image cannot be inspected. It requires
the fallback to run as `appuser`, requires matching release environment/label
metadata, rejects baked-in application/database secret keys, runs `pip check`
and the blocking image scan, and only then creates the timestamped rollback tag.
The normal exact-image path remains unchanged.

Never reset/reseed the live bank during routine deployment: question IDs are
referenced by local progress. Startup runs pending migrations and collectstatic.
The API has three workers, 30-second request/graceful timeouts, a 45-second
container shutdown grace period, and a bounded 60-second database startup probe
(`DB_STARTUP_TIMEOUT_SECONDS`, 1..300). Failed migrations stop startup.
The non-root backend filesystem is read-only except the existing static/media
volumes and a 64 MB temporary filesystem. Capabilities are dropped, privilege
escalation is disabled, and the backend is capped at 512 MB and 128 processes.
PostgreSQL starts directly as its non-root user with a read-only root filesystem,
all capabilities dropped, `no-new-privileges`, 512 MB/128-process limits and bounded
noexec tmpfs mounts for `/tmp` and its Unix socket. Only the external PGDATA volume
is persistent and writable, and no database port is published to the host. Its local
image extends a digest-pinned PostgreSQL 16.15 Alpine base only to remove the unused
root-only `gosu` switcher and its independently compiled runtime.
Fresh clusters bootstrap `pcep_admin` as the system-object owner and create a
separate `pcep_user` login for Django. The application role owns only its database
and public application objects; it cannot create roles or databases, replicate,
bypass row security or act as a superuser. Only the database service receives
`.env.db`, so the administrator credential never enters the backend container.
Healthchecks use the first configured allowed hostname and forwarded HTTPS;
local hostnames are not required in production ALLOWED_HOSTS. `/api/health/`
remains readiness. Successful Compose probes carry an internal marker and are
omitted from Gunicorn's access log only when they arrive from container loopback.
Failed probes and public requests remain visible, including requests that copy
the marker. Gunicorn logs request ID, method, path, status and duration, without
bodies, cookies, authorization or query strings.

## Frontend Deploy

```bash
make deploy-frontend
curl -fsS https://pcep.micutu.com/ >/dev/null
```

The target checks the pinned runtime, completes the build and validates required
files and referenced HTML assets. It copies to a staging directory on the live
filesystem, backs up the current root under BACKUP_ROOT, retains hashed assets
from the last seven days for open tabs, then uses Linux renameat2 directory
exchange. The complete immediately previous asset generation is always retained,
even after a longer deployment gap. Older generations are omitted only from the
new staging root; the complete previous root and external backup remain available.
Copy, validation and exchange failures leave the live root intact. The previous
root is retained beside it as `.frontend.previous-<timestamp>-<id>`.
`FRONTEND_ROOT`, `BACKUP_ROOT`, `PYTHON` and `ASSET_RETENTION_DAYS` can be
overridden; asset retention accepts 1 through 365 days. Python accepts relative
paths, absolute paths or executables from PATH. Linux atomic exchange support is
required; the script refuses to fall back to delete-then-copy.
No automatic snapshot deletion is performed. Preview bounded retention with
`make release-retention` (five newest rollback roots and five newest backup
copies by default). The preview recognizes only exact `frontend`/`static`
release names and reports allocated space without following symlinks. It cannot
select database dumps, `security-*` directories or other backup files. After
reviewing every listed path, apply the exact plan explicitly with:

```bash
backend/.venv/bin/python scripts/release_retention.py \
  /var/www/pcep/frontend --backup-root /home/micu/backups/pcep \
  --keep 5 --apply
```

Keep at least two complete snapshots; the utility rejects a lower value. Run the
dry-run again after cleanup and verify a retained rollback directory before the
next deployment.
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
Question-content migrations 0003 through 0006 update existing rows in place,
preserve question/choice IDs and are reversible; they need no database restore
for an application rollback. Database restoration is a separate planned
maintenance operation into a suitable database, never an automatic pipe into the
running production database.

PostgreSQL runtime changes require a fresh verified logical backup, a successful
`scripts/check_postgres_container.sh` run and a clean `make audit-db-image` result.
Build and recreate only the database service, then wait for both database and backend
readiness before public smoke testing:

```bash
docker compose build db
make audit-db-image
docker compose up -d --no-deps --no-build db
docker compose ps
make production-smoke
```

Tag the previous database image before replacement. To roll back the image while
preserving the named PGDATA volume, retag it as
`pcep_webapp-postgres:16.15-alpine3.24`, recreate only `db` with `--no-build`, and
repeat the readiness and public smoke checks. Restoring a logical dump remains a
separate planned data operation and is not part of an image rollback.

When rotating the Django database password, update `POSTGRES_PASSWORD` in `.env`
and `PCEP_APP_PASSWORD` in `.env.db` atomically with the role password, then
recreate only `backend`. Rotating the administrator password updates the
`pcep_admin` role and `POSTGRES_PASSWORD` in `.env.db`; never add that value to
`.env` or the backend service.

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
The frontend treats feedback as an untrusted API boundary: Practice, Exam and
Flashcards bind it to the requested question and selected choice, verify that the
correctness flag agrees with the returned correct choice, require both explanation
strings, reject fields outside the documented response contract and retain only the
four canonical feedback fields. A rejected Practice response leaves the current
question answerable so the learner can retry without recording a false result.
Exam review keeps each picked choice from the validated local grading payload; it
does not depend on identifiers being copied into the canonical feedback object.
`GET /api/search/` accepts a required 2–80 character `q`, optional valid module,
PCEP-30-02 objective and difficulty filters, and a `limit` from 1 to 20. It
performs one bounded query and returns only question ID, text, code, module,
objective and difficulty. Choices,
explanations and answer metadata are deliberately absent. A selected drill sends
only unique IDs to `quiz-set`, which returns fresh public choices under the
existing answer-leakage contract. ID-targeted requests preserve the requested order
after optional scope filters and apply `count` to that order; only ordinary unlisted
quiz sets are randomized. The learner may launch those selected IDs as Practice or
Flashcards; Flashcards use the same validated recovery format and never persist
answer metadata for an unrevealed question.
Editing the search term immediately aborts an in-flight request and clears its
results and selection. A late response for an older term therefore cannot appear
under the new query or launch a stale drill. Changing module, objective or difficulty
remounts the search boundary and provides the same cancellation behavior.
`GET /api/stats/` reports counts for all 15 objectives, and `quiz-set` accepts the
same objective filter. A module/objective mismatch is rejected instead of silently
returning an empty set. The full-mock preset rejects objective filters because its
distribution is fixed at module level.
`GET /api/quiz-set/?preset=pcep-30-02&count=30` returns an exact 7/8/7/8
module distribution for the 30-question, 40-minute full-mock flow. Preset
requests reject `ids`, module, objective or difficulty combinations, fail closed with 503
if any module lacks enough questions, and use the same public serializer as
other question reads. The preset models PCEP-30-02 timing and syllabus item
counts; the product discloses that its questions are single-choice while the
official exam also has multiple-select and interactive formats.
Custom Practice, Exam and Flashcard setup offers 5, 10, 20, 30 and 50 questions.
The five-question option remains random and filter-aware; it is separate from the
deterministic, syllabus-balanced daily challenge. If a selected scope contains fewer
questions than the chosen size, the API returns every available match and the active
session/timer use that actual count. The chosen size remains the setup preference for
the next quiz instead of being replaced by the temporary smaller result.
If the initial question request fails, the error screen offers a direct Retry with the
exact saved mode, filters, preset or targeted IDs. Back to setup remains available.
The normal loading guard prevents a second concurrent start while either request is in
flight; no active recovery record is created until a valid public question set arrives.
While that request is in flight, Cancel loading aborts it and returns to setup with the
chosen preferences intact. A late response cannot start a session or create recovery.
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
validates the complete inline set with the same snippet, syllabus, explanation
quality and exact-duplicate rules as the audit command. Its question list shows
the correct option (or an invalid-count warning) from one prefetched choice set;
the separate choice admin is view-only.
Migration `0011_choice_one_correct_choice_per_question` adds a partial unique
constraint that rejects a second correct choice for the same question even when
a write bypasses Django validation. PostgreSQL cannot express the complementary
cross-row requirement that a question has at least one correct choice with a
simple check constraint, so Admin, seed preflight, deployment audit and the API's
fail-closed 503 response continue to enforce and detect that half of the invariant.
Seed validation runs before any writes, including an explicitly requested reset.
Every question has one reviewed primary syllabus objective. The audit rejects
unknown or cross-module objectives and warns if any of the 15 objectives is empty.
The curated position table is protected by a content digest for each module, so a
question edit or reorder requires an explicit taxonomy review. The syllabus audit
also parses valid snippets and rejects set literals, set
comprehensions and `set()` calls because PCEP-30-02 defines its data-collection
scope as lists, tuples, dictionaries and strings. Invalid snippets used for syntax
questions retain the existing normalized-source fallback.
Migration `0003_label_empty_output_choice` changes only the empty wrong option
for `print(0 or "" or "x" or "y")` to `(empty output)`, preserving all IDs and
explanations. It is reversible and does not recreate the question bank.

## Local progress and portability

Progress now uses the versioned `pcep.progress` record. Valid legacy
`pcep.history`/`pcep.mistakes` records are read and migrate only after a complete
successful write. A failed import leaves the previous record intact. Each list
for history, mistakes, bookmarks and personal notes is bounded to 100 records;
each note is limited to 2,000 characters. The per-question review schedule is
bounded to 1,000 compact records. The progress screen exports backup format v4,
previews and merges strictly validated imports up to 8 MB, and still accepts
existing v1, v2 and v3 backups. If multiple files are selected while reads are in
flight, only the most recent selection can update the preview or error state.
History, mistakes, bookmarks, notes and the review schedule can be reset
independently. Backups contain public question options,
aggregate performance, optional confidence ratings, daily challenge dates,
bounded response-time totals, the optional `pcep-30-02` full-mock marker, review
dates and user-written notes, never answer keys or explanations. Keep backups
private if you want to keep your study history and notes private; nothing is
uploaded by these features.

Quiz setup accepts only the supported 5, 10, 20, 30 and 50 question preferences.
Older `pcep.settings` records that contain an actual short-scope result such as 1
are normalized to the 30-question default when setup reads them. This read is
non-destructive; storage changes only after the learner explicitly starts another
session. Active Practice, Exam and Flashcard recovery records continue to accept
their validated actual lengths from 1 through 100, so a short saved session is not
discarded by the preference migration.

Bookmarks are available on question cards. Bookmark and mistake drills fetch
current public question data using the bounded `ids` quiz-set filter, avoiding
stale choice IDs after admin edits. Targeted lists retain their intent order and
include up to 100 unique questions, matching the API and recovery limits instead
of silently truncating longer saved lists. Module/difficulty accuracy includes mixed
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
question data. The learner can answer that set in Practice or self-rate it as
Flashcards; the latter uses the same answer-safe reveal and crash-recovery path as a
custom deck. The schedule stores no choices, selected choice IDs, explanations or
correctness key. An optional per-question confidence value (`low`, `medium` or `high`)
is stored with the latest review. Dashboard mastery combines observed accuracy,
repetition and the achieved interval, and should be treated as a study signal rather
than an exam credential.

Adaptive study is also local and rule based. It ranks at most 20 unique question
IDs using a documented score: +100 when due, +60 while in the mistakes list, up to
+40 from observed error rate, up to +30 from the mastery gap, +20 when the latest
confidence is low, and a small +5/+10 medium/hard bonus. Questions at or above 80%
mastery are omitted unless currently due, missed or their latest recorded confidence
is low. Equal scores prefer the least recently attempted question, then its numeric
ID, so the plan is deterministic and testable. The ranked set can launch graded
Practice or self-rated Flashcards. Only the selected IDs are sent to `quiz-set`;
fresh public questions come back in the ranked priority order without answer metadata,
and Flashcards use the same validated answer-safe recovery path as every other custom
deck.

Dashboard momentum is derived only from the bounded local attempt history. Study
streaks count unique local calendar days and remain current through the day after
the latest session. Score trends compare up to five recent graded sessions with
an equally sized preceding window using question-weighted accuracy. Average pace
prefers measured time to the first answer for sessions created by this version;
legacy sessions fall back to total elapsed time divided by graded questions.
Confidence calibration compares aggregate high-confidence misses and
low-confidence successes. Flashcards count as study activity but are excluded from
performance, confidence calibration and pace because their result is self-rated.

## Active session recovery

Completion uses the active recovery record's ownership ID as the durable attempt ID
for Exam, Practice and Flashcards. The report opens only after the combined progress
snapshot is written and the matching recovery record is removed. If cleanup is blocked,
the last screen remains available for retry; finding that attempt ID in history makes the
retry idempotent, so history, mistakes and spaced-repetition counters are not applied a
second time. A recovery record owned by another tab is never removed.

### Exams

An in-progress exam is stored separately under the versioned
`pcep.activeExam` key. It contains only sanitized public questions, the learner's
selected choice IDs, optional confidence ratings, bounded time-to-first-answer
values, flags, current index, start time and original deadline. It never contains
correctness flags, explanations or a correct-choice ID, and it is not included in
progress exports. Only one active exam is retained. A failed grading request keeps
the exact answer, confidence and timing snapshot for a safe retry.

Each active exam also has an opaque local session ID. Resuming it rotates that
ID and transfers write ownership to the current tab. Other open tabs detect the
storage change, leave their stale in-memory exam and show the newly saved copy;
their later saves, completion cleanup or Quit action cannot overwrite or delete
the current owner's recovery data. An in-flight grading request is aborted on the
same conflict, and ownership is checked again before a result is persisted.
Recovery snapshots created before session IDs were introduced receive a
deterministic legacy ID when read and remain resumable.

On reload the setup screen requires an explicit choice: resume the saved exam or
discard it before starting any quiz or dashboard drill. The recovery countdown
uses the original wall-clock deadline and refreshes after timer suspension, focus
or visibility changes. Discard requires a second explicit confirmation. If the
deadline passes, the action changes to grading the locked saved answers; a network
failure keeps the recovery copy for retry. Successful grading, Quit and confirmed
Discard remove it. Strict schema validation rejects unknown questions/choices,
duplicate flags, invalid timestamps and extra top-level fields. Abandoned data
expires 24 hours after its deadline. Storage failure uses the existing persistence
warning and never blocks the live in-memory exam.

### Practice

An in-progress Practice session is stored separately under the versioned
`pcep.activePractice` key. The snapshot contains sanitized public questions,
current position, confidence, start time and an opaque ownership ID. Completed
items may contain feedback because the learner has already submitted those exact
answers. Every unanswered question passes through the public-question whitelist,
so its correct choice, explanations and correctness flags are never stored.
Practice recovery is local to the browser and is excluded from progress exports.

The snapshot is updated after a confidence change, successful submission or move
to the next question. Reload offers an explicit Resume or confirmed Discard;
resuming submitted feedback does not repeat the API request. Successful completion
records one normal attempt and removes the snapshot, while Quit discards it. Strict
validation binds every completed item to the corresponding question and choice,
checks correctness against the returned correct choice, bounds explanations and
response times, rejects unknown fields and expires snapshots after 24 hours.

Resuming rotates the Practice session ID. A stale tab detects the ownership change,
aborts an answer request in flight, returns to the recovery screen and cannot
overwrite or clear the new owner's copy. Browser storage failure raises the normal
persistence warning but does not block the in-memory session.

### Flashcards

Flashcards obtain the answer through the same rate-limited submission endpoint as
Practice, so the initial deck remains answer-safe. The reveal request carries an
AbortSignal and is cancelled on Quit or component teardown. Late responses cannot
update a different card. Returned feedback passes the shared strict validator before
rendering: the question and correct-choice relationship, booleans and bounded
explanation strings must all be valid. A malformed or failed response leaves the card
unrevealed and offers the normal retry path; it cannot be self-rated until valid
feedback arrives.

After a successful reveal, focus moves to **Review later** so the removed Reveal
button never leaves keyboard focus stranded. `1` selects **Review later** and `2`
selects **Got it**; Space or Enter reveals an unrevealed card. The controls expose
the same bindings through `aria-keyshortcuts`, the footer lists them, and the shared
shortcut guard suppresses them in editable fields, during composition, on key repeat
and with browser modifier keys.

An in-progress deck is stored under the versioned `pcep.activeFlashcards` key and
expires after 24 hours. The snapshot contains the sanitized public deck, current
position, completed self-ratings, start time and an opaque ownership ID. It may retain
the answer for the current card only after that learner has revealed it; all later
cards still pass through the public-question whitelist and contain no answer metadata.
The snapshot is local to the browser and excluded from progress exports.

Due reviews, saved mistakes and bookmarks may all start Flashcard decks. Each path
sends only bounded question IDs, fetches the current public question representation
from the API and then uses the same recovery boundary described above. A Flashcard
self-rating updates the existing local mistake and review schedule semantics; saved
bookmarks remain explicitly managed by the learner.

Reload offers explicit Resume or confirmed Discard. A revealed current card resumes
without repeating its answer request, while an unrevealed card returns cleanly.
Successful completion records one attempt and clears the snapshot; Quit discards it.
Strict validation binds completed ratings to their positional questions and correct
choices, bounds explanations, rejects unknown fields and enforces the deck/config
size. Resume rotates the session ID. A stale tab detects that ownership transfer,
aborts any reveal in flight, returns to the recovery screen and cannot overwrite or
delete the new owner's copy.

Practice, Exam and Flashcards now enter the completed report only after the combined
history, mistakes and study snapshot is stored successfully. If quota, permissions or
a newer schema prevents that write, the current mode and its active recovery record
remain intact. Practice exposes **Retry saving results**, Exam exposes **Retry
submission**, and the final Flashcard rating becomes selectable again. A successful
retry records the attempt once and only then clears the active recovery record.
The global persistence warning clears after a later storage write succeeds, so a
recovered browser does not continue reporting a stale failure. Failure and recovery
signals are tracked per storage key: saving a smaller active-session record cannot
hide a failed `pcep.progress` snapshot.

Progress, settings and active-session writes refuse to replace a storage schema
with a higher version number. A stale tab also leaves newer recovery data untouched
on read and clear, and shows a reload warning immediately or after a cross-tab
storage change. This prevents an older cached bundle from deleting data written by
a newer release.

Current-version progress writes emit an in-tab change signal, while other tabs use
the browser's `storage` event. Setup counters, the open dashboard and bookmark
controls therefore refresh without polling or a page reload. A personal note that
changes elsewhere refreshes while it is only being viewed. If the learner already
has that note open for editing, Save preserves the draft and reports the conflict;
a second deliberate Save may replace the newer stored note.

The Python runner limits source to 20,000 characters, output/tracebacks to
10,000 characters, queued/running jobs to four, startup to 30 seconds and each
execution to eight seconds. Timeout terminates the worker; later Run recreates
it. Failed startup/crash also permits retry. Both the worker and its manager enforce
the output bound; if either layer discards excess text or chunks, the result is marked
as truncated so the UI does not present incomplete output as complete. These are
responsiveness/resource protections, not a hardened sandbox: arbitrary Python can
use the JavaScript bridge and can still exhaust browser memory before a timeout.
Do not run untrusted snippets in an authenticated admin browser.

The question audit canonicalizes valid Python snippets through the standard AST
before duplicate comparison. This catches semantically identical questions that
differ only in quote style or harmless formatting. Intentionally invalid teaching
snippets fall back to normalized source comparison and are not rejected merely for
being invalid Python. Every explanation must also contain at least 20 non-whitespace
characters. Strong editorial markers such as TODO/FIXME text, self-correction notes,
"original intent" or a failed-distractor remark are integrity errors in both seed and
database audit modes, so drafting artifacts cannot silently reach answer feedback.

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
Migration `0006_replace_out_of_syllabus_sets` replaces two equivalent set
questions with distinct `dict.values()` and dynamic `dict.items()` exercises from
objective 3.3. It updates rows and choices in place so local bookmarks and saved
exam selections keep valid IDs.
Migration `0007_add_question_objective` assigns the reviewed objective to existing
rows through frozen question signatures, then adds a database constraint requiring
the objective to belong to its module. It refuses unknown production questions
instead of assigning a guess. After migration, run `python manage.py seed_questions`
without `--update` or `--reset`; this safely creates only the four new questions
covering objectives 1.1 and 1.2 and preserves all existing question and choice IDs.

`seed_questions --update` is reserved for restoring reviewed fields on rows that
already have the expected four choices. It updates those choices in ID order and
preserves every question and choice ID. If a matching question has a structural
difference, such as a missing choice, the entire transaction is refused; repair
that case with a reviewed data migration rather than deleting and recreating rows.

Migrations `0008_replace_out_of_scope_constructs` and
`0009_replace_near_duplicate_questions` revise reviewed rows in place while
preserving their IDs and correct-option positions. Migration
`0010_add_foundations_coverage` adds three medium questions for the previously
thin lexis, keyword and instruction topics under objectives 1.1 and 1.2. It is a
no-op on an empty database because a later `seed_questions` run installs the
complete bank; on an existing bank it validates any matching row and refuses to
overwrite divergent content.

## Nginx production topology and hardening

The tracked vhost now matches the existing TLS deployment, including SEO,
ACME, sitemap and robots routes. It requires the installed Let's Encrypt
certificate, shared `block-dotfiles.conf`, and host Cloudflare real-IP and
`$from_cloudflare_origin` definitions. The shared tunnel connects to HTTPS
loopback; Nginx restores CF-Connecting-IP only for trusted peers and overwrites
X-Forwarded-For with that verified address. Django still trusts one proxy hop.

PCEP has an explicit ingress rule before the shared HTTPS catch-all. It fixes the
origin Host and SNI to the reviewed hostname and verifies the local Let's Encrypt
certificate, overriding the legacy global `noTLSVerify` only for PCEP:

```yaml
- hostname: pcep.micutu.com
  service: https://127.0.0.1:443
  originRequest:
    originServerName: pcep.micutu.com
    httpHostHeader: pcep.micutu.com
    noTLSVerify: false
    connectTimeout: 10s
```

Keep this rule after path/special-service rules and before the catch-all. Validate
the file and selected route, verify the origin certificate independently, then
restart because this systemd service has no reload action:

```bash
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule \
  https://pcep.micutu.com/api/health/
openssl s_client -connect 127.0.0.1:443 -servername pcep.micutu.com \
  -verify_return_error -brief </dev/null
sudo systemctl restart cloudflared
make production-smoke
```

The pre-change mode-0600 backup is
`/home/micu/backups/pcep/cloudflared.config.20261004T123936Z.yml`. To roll back,
install it over `/etc/cloudflared/config.yml` as `root:root` mode 0600, validate,
restart only cloudflared and rerun the smoke. The restart reconnects the tunnel and
can briefly return an edge 530; it does not require an Nginx, Docker or database
restart.

Install `nginx/snippets/pcep-*.conf` into `/etc/nginx/snippets/` before installing
the vhost. Back up outside sites-enabled, run `sudo nginx -t`, then use
`sudo systemctl reload nginx` (graceful). The 2026-09-18 vhost backup is in
`/home/micu/backups/pcep/security-20260918/nginx.before`.

The public vhost deliberately returns 404 for both `/admin` and `/admin/`. Do not
restore the Django admin proxy on the learner origin. A future operator interface
requires a separate origin protected by Cloudflare Access (or equivalent),
phishing-resistant MFA, explicit operator enrollment and a tested emergency access
procedure before its Nginx route is enabled.
The API has a shared 3 requests/second IP limit with a burst of 30, 64 KB body
limit, short connection timeout and JSON 413/429 errors. Those Nginx-generated
errors carry `Cache-Control: no-store` and the same restrictive API CSP
(`default-src 'none'; frame-ancestors 'none'`) as proxied API responses. Admin
retains its 20/minute limit and Django CSRF behavior. The analytics proxy exposes only
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
and manages focus; quitting Practice, Exam or Flashcards asks before clearing the
recoverable session.
Question/result headings receive focus on navigation; answer options and
workspace navigation use native buttons. A skip link, visible focus, scrollable
keyboard-accessible code and reduced-motion styles apply throughout.
Keyboard help is available in the footer. Shortcuts ignore typing, modifiers,
composition and repeated keys. Offline and persistence warnings explain recovery.
A completed report can immediately refetch its ordered misses and low-confidence
correct answers as answer-safe Practice or Flashcards; the saved active session
still contains only public question fields until each answer is submitted/revealed.
A failed screen/chunk load offers reload and states the unsubmitted-session risk.
Axe and overflow checks run through the study screens in both themes at
360/390/430/768/1024/1280/1440 px; they supplement manual inspection, not a claim
of complete accessibility certification.

## PWA update and cache policy

`frontend/pwa.config.js` contains the tested cache policy. Only the public shell
is precached. Runtime caching accepts HTTP 200 same-origin `/pyodide/` files in
`pyodide-runtime-0.29.4`; opaque responses and API feedback are excluded.
API/admin/static/media, study pages, analytics, asset/runtime paths and
robots/sitemap are exempt from offline SPA navigation fallback. A newly installed
worker remains waiting and shows a notice; the Reload action sends the worker's
`SKIP_WAITING` message after the learner finishes the session. The worker claims
the page only after that explicit activation, then the page reloads under the new
shell. Active tabs are not automatically reloaded. The download script validates
every pinned core file and stages downloads before replacing build inputs,
preserving an older runtime on failure. No answer database is downloaded for
offline use.
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
`scripts/check_nginx.sh` first performs `nginx -t`, then boots that temporary TLS
vhost on a random loopback port. It verifies the complete Nginx-generated 413 and
429 API contracts: status, exact JSON body, no-store policy, restrictive CSP,
request ID and `Retry-After` on throttling. The script uses a digest-pinned Nginx
image, removes its container and temporary files on exit, and never contacts the
production hostname.
Browser tests use mocked APIs; Python execution uses the real self-hosted runtime.
The push/pull-request CI never calls production. The scheduled dependency audit
only reads manifests and advisory services; the separate scheduled smoke workflow
performs only the bounded public checks documented above.

CI also supports an explicit manual dispatch so an operator can validate the exact
current `main` commit if GitHub misses a push event. This does not replace PR checks
or bypass branch protection:

```bash
gh workflow run ci.yml --ref main
gh run list --workflow ci.yml --branch main --event workflow_dispatch --limit 1
gh run watch <run-id> --exit-status
```
