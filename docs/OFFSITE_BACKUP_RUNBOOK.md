# Offsite database backup security and incident runbook

Status: **BLOCKED FOR ACTIVATION**. The implementation is ready for review, but no
offsite upload or automatic trigger is authorized until every activation gate below
is complete.

## CISO review — 2026-10-05

### Threat model

The top three STRIDE risks, ordered by likelihood multiplied by impact, are:

1. **Information disclosure — high impact.** A raw backend or leaked rclone config
   and crypt material could expose the full database dump. The live database
   currently has zero Django users and zero server-side sessions, but its schema can
   later contain usernames, email addresses, password hashes and session data. Loss
   of the only crypt recovery copy would instead destroy off-host recoverability.
2. **Denial of service — medium likelihood.** Expired/revoked credentials, provider
   outage or the retiring shared Google Drive client ID can silently eliminate the
   off-host recovery point unless failure reaches an operator.
3. **Tampering — high impact.** Compromised storage credentials could replace or
   delete remote objects. Client-side encryption protects confidentiality, not
   availability; provider versioning or object lock and independent alerts are
   still required.

Spoofing is reduced by a dedicated least-privilege provider credential. Repudiation
requires provider audit logs retained outside the bucket/account. Elevation of
privilege is limited by the non-root systemd service and read-only host paths.

### Blast radius and cost

The 2026-10-05 live aggregate is zero Django users, zero Django sessions, 308
questions and 1,232 choices. Current disclosure would expose the complete question
bank and schema, not browser-local learner progress. Worst case after future account
use is every database record, account identifier, password hash and active session.
The affected-user count is currently zero and must be recalculated before activation
if accounts or server-side learner data are added.

A defensible annual loss expectancy cannot be calculated from the available inputs:
there is no incident-frequency, revenue-impact, response-cost or contractual data.
Do not substitute an invented monetary estimate; record those inputs before a vendor
approval decision.

### Detection

Target MTTD is under 24 hours. The scheduled job fails on stale local backup, remote
diagnostics, unencrypted configuration, transfer errors or round-trip checksum
mismatch. Journal entries alone are not detection. Current MTTD is therefore
unbounded until an independent monitor pages an operator when the service fails or
fails to update its atomic success marker within 24 hours. Automatic activation is
blocked until that alert and its owner are documented and tested.

### Response

For an alert or suspected compromise:

1. Mask `pcep-db-offsite.service` and remove the PCEP backup `OnSuccess` drop-in; do
   not delete local backups or remote evidence.
2. Preserve the relevant systemd journal and provider audit log with UTC timestamps.
3. Revoke the provider token. If the rclone config or crypt passwords may be exposed,
   treat every remote dump as disclosed and rotate both crypt secrets before the next
   upload.
4. Inventory current `auth_user` and `django_session` counts without exporting row
   contents. Reset administrator passwords and invalidate sessions when those tables
   are non-empty or exposure cannot be excluded.
5. Verify all local checksums and run `make verify-database-restore`. Restore only
   into an isolated database, never over production during investigation.
6. Create a new dedicated remote path and credential. Do not reuse the suspected
   destination or encryption key.
7. Determine whether personal data was exposed, start the notification clock when
   awareness is established, and record the incident decision and evidence.
8. Tabletop this sequence before activation and after any provider/key change.

### Regulatory window

No current learner PII is stored server-side. If future database contents include
personal data, GDPR notification to the supervisory authority may be required within
72 hours of awareness when the breach is likely to risk individuals, as specified by
[GDPR Article 33](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/).
Contractual, national and provider-notification duties still require case-specific
review. No claim of SOC 2, ISO 27001, HIPAA or payment-card scope is made.

### Vendor and supply chain

No new vendor is approved by this change. Google Drive is blocked because the
configured crypt remote depends on rclone's retiring shared OAuth client. The current
R2 remote is blocked because it is a raw S3 backend without a dedicated PCEP crypt
wrapper. A DPA, subprocessor decision, provider security review, regional/storage
location and versioning/object-lock settings have not yet been recorded.

**Verdict: 🔴 BLOCK activation.** Mitigate the gates below, repeat this review, then
perform a manually observed first upload and restore before installing the automatic
`OnSuccess` trigger.

## Activation gates

- Create a PCEP-only provider bucket/folder and least-privilege credential.
- Create an rclone `crypt` remote wrapping a non-root PCEP-only backend path.
- Explicitly use standard filename encryption, directory-name encryption, a strong
  password and a distinct second salt.
- Store the crypt recovery material in an independently controlled offline secret
  store; losing it makes every remote backup unrecoverable.
- Enable and verify provider versioning or object lock plus independently retained
  access/audit logs.
- Configure an independent failure/missed-success alert with a named responder and
  MTTD under 24 hours; run a real alert test.
- Review the provider DPA, subprocessors and data region.
- Run `make offsite-backup-preflight` and a manually observed first
  `make offsite-backup` followed by `make verify-database-restore`.
- Tabletop the response steps above and record the date and participants.

## Safe configuration and operation

The environment file contains only the crypt remote path, not credentials:

```text
PCEP_OFFSITE_REMOTE=pcep-r2-crypt:pcep/database/daily
```

Store it as root-owned mode `0600` at `/etc/pcep/offsite-backup.env`. Create a
minimal PCEP-only rclone configuration containing only the dedicated backend and its
crypt wrapper. Manual commands require its explicit path and mode `0600`; they never
fall back to the operator's multi-application config. The systemd service loads an
encrypted credential from `/etc/credstore.encrypted/pcep-rclone-config`, copies it to
a private runtime tmpfs for the duration of the job, and never reads the operator's
config. Keep an independently controlled encrypted recovery copy: the host-bound
systemd credential alone cannot recover backups after total host loss.

Before upload, the script requires a real mode-`0600` config owned by the service
user and checks the redacted remote definition. It accepts only `type=crypt` with
explicit standard filename encryption, directory encryption, both crypt secrets and
a non-root wrapped backend path. The wrapped backend must use the same bounded safe
name/path grammar as the destination: absolute paths, empty or repeated segments,
traversal and self-wrapping crypt remotes are rejected. Any rclone diagnostic fails
the run, including the shared-Google-client retirement notice.

The job selects the newest private backup/checksum pair, verifies all complete local
pairs and rejects a scheduled backup older than six hours. It uploads with immutable
`copyto` operations, uploads the checksum marker last, downloads both objects through
the crypt remote into a private temporary directory, verifies SHA-256 and verifies
the local source again. Only then does it atomically update a mode-`0600` success
marker for the independent monitor. It never runs `sync`, `delete`, `deletefile` or
`purge`, and does not implement remote retention. Automatic execution is chained to
a successful local backup via a separately installed systemd `OnSuccess` drop-in;
there is no independent timer that can report success for yesterday's dump.

Only after all activation gates pass:

```bash
PCEP_OFFSITE_REMOTE=pcep-r2-crypt:pcep/database/daily \
OFFSITE_RCLONE_CONFIG=/secure/staging/pcep-rclone.conf \
  make offsite-backup-preflight
PCEP_OFFSITE_REMOTE=pcep-r2-crypt:pcep/database/daily \
OFFSITE_RCLONE_CONFIG=/secure/staging/pcep-rclone.conf make offsite-backup

sudo install -d -m 0700 -o root -g root /etc/pcep
sudo install -d -m 0700 -o root -g root /etc/credstore.encrypted
sudo install -m 0600 -o root -g root /path/to/offsite-backup.env \
  /etc/pcep/offsite-backup.env
sudo systemd-creds encrypt --name=rclone.conf \
  /secure/staging/pcep-rclone.conf \
  /etc/credstore.encrypted/pcep-rclone-config
sudo install -m 0644 ops/systemd/pcep-db-offsite.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start pcep-db-offsite.service

# Only after the manual service, alert and missed-heartbeat checks pass:
sudo install -d -m 0755 /etc/systemd/system/pcep-db-backup.service.d
sudo install -m 0644 ops/systemd/pcep-db-backup.service.d/20-offsite.conf \
  /etc/systemd/system/pcep-db-backup.service.d/20-offsite.conf
sudo systemctl daemon-reload
```

Inspect the first run with `journalctl -u pcep-db-offsite.service`. Confirm a success
heartbeat and a failure page before installing the `OnSuccess` drop-in. The health
monitor should read `/var/lib/pcep-db-offsite/last-success` as root and alert when its
UTC timestamp is older than 24 hours. Remove the plaintext staging config after its
offline recovery copy and encrypted systemd credential have both been verified.
