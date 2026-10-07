# Offsite database backup security and incident runbook

Status: **BLOCKED FOR ACTIVATION**. The implementation is ready for review, but no
offsite upload or automatic trigger is authorized until every activation gate below
is complete.

## CISO review — 2026-10-05, R2 profile reviewed 2026-10-07

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
configured crypt remote depends on rclone's retiring shared OAuth client. The
operator's current R2 remote is also blocked: it is shared, raw S3 storage with
unknown credential scope and no dedicated PCEP crypt wrapper.

Cloudflare's official controls make a **new**, PCEP-only R2 bucket a technically
eligible candidate, but not an approved destination. It must be created in the
[EU jurisdiction](https://developers.cloudflare.com/r2/reference/data-location/)
rather than with a best-effort location hint, use a
[bucket-scoped Object Read & Write token](https://developers.cloudflare.com/r2/api/tokens/),
and protect the encrypted prefix with a native
[R2 Bucket Lock](https://developers.cloudflare.com/r2/buckets/bucket-locks/). R2
does not implement the standard S3 versioning or S3 Object Lock interfaces, so do
not claim either control; record the native Bucket Lock rule instead. Cloudflare
[Audit Logs](https://developers.cloudflare.com/r2/platform/audit-logs/) cover
configuration changes, not object access.
[Data Access Logs](https://developers.cloudflare.com/r2/buckets/data-access-logs/)
are best-effort, incomplete and generally available only for buckets without a
jurisdiction, so they cannot replace the independent missed-success alert. The DPA,
subprocessor decision and account terms still require owner review.

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

## Reviewed Cloudflare R2 candidate profile

This profile narrows the acceptable R2 design; it does not authorize bucket creation
or upload. Record screenshots or exported settings without secret values for every
item before changing the verdict:

- Create a new private bucket for PCEP with **EU jurisdiction** at creation. A
  Western/Eastern Europe location hint is not equivalent. Jurisdiction cannot be
  changed later. Keep `r2.dev` access and custom public domains disabled.
- Create an R2 **Object Read & Write** token scoped only to that bucket. Do not put an
  Admin token or a token able to create/delete buckets or edit Bucket Lock rules on
  the application host. Set an expiry/rotation date and a named owner.
- Add a native R2 Bucket Lock rule for the physical `encrypted/` prefix with at least
  30 days of age-based retention. This matches the clear prefix in the backend
  remote; names below it are encrypted by rclone. Verify the rule using an account
  identity separate from the host token, and record its rule ID and retention.
- Retain Cloudflare account audit evidence outside the bucket and alert a named
  operator on bucket deletion, visibility/lifecycle changes, token changes and
  Bucket Lock changes where the account tooling exposes them. Independently alert
  when `/var/lib/pcep-db-offsite/last-success` is older than 24 hours; provider logs
  alone do not satisfy this gate.
- Review and record the current Cloudflare DPA, subprocessors, billing/retention
  impact and account-recovery/MFA controls. A 30-day Bucket Lock can increase storage
  and prevents overwrite/deletion while its rule applies.

Build the dedicated config interactively and store only the resulting mode-`0600`
file. The required shape is shown below with placeholders; do not commit a populated
copy. Cloudflare R2's
[S3 compatibility table](https://developers.cloudflare.com/r2/api/s3/api/) marks
ACL headers, bucket versioning and standard S3 Object Lock as unsupported, so no
`acl` option is specified. `no_check_bucket` prevents rclone from attempting bucket
creation and supports the least-privilege host token.

```ini
[pcep-r2-eu]
type = s3
provider = Cloudflare
access_key_id = <DEDICATED_BUCKET_SCOPED_ACCESS_KEY_ID>
secret_access_key = <DEDICATED_SECRET_ACCESS_KEY>
endpoint = https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com
region = auto
no_check_bucket = true

[pcep-r2-crypt]
type = crypt
remote = pcep-r2-eu:<PCEP_ONLY_BUCKET>/encrypted
password = <RCLONE_OBSCURED_STRONG_PASSWORD>
password2 = <RCLONE_OBSCURED_DISTINCT_SECOND_SALT>
filename_encryption = standard
directory_name_encryption = true
```

The two crypt values must be generated independently through rclone's supported
configuration flow. Rclone's obscured representation is not a secret-management
control; protection comes from the encrypted systemd credential and the separate
offline recovery copy. The environment destination remains below the wrapper:

```text
PCEP_OFFSITE_REMOTE=pcep-r2-crypt:pcep/database/daily
```

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
