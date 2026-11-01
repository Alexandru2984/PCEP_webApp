# Security incident response runbook

Status: **active**, with notification and tabletop gaps recorded below.

Owner: repository owner and production server operator. If one person holds both
roles, keep a timestamped incident log and ask an independent trusted person to
review containment and recovery decisions before restoring service.

Last technical review: 2026-10-13. Last human tabletop: **not completed**. Review
this runbook after every incident, material architecture or vendor change, and at
least every six months.

## Scope and known blast radius

This runbook covers the public learner and runner origins, the GitHub repository and
Actions control plane, Cloudflare ingress, Nginx, the production host, Docker,
PostgreSQL, local backups and the inactive offsite-backup path.

The production database check on 2026-10-08 found zero Django users, zero Django
sessions, 308 questions and 1,232 choices. Recalculate those counts during every
incident; the schema can hold account and session data even though the current
application does not create accounts or store learner submissions. Progress,
bookmarks and notes live in each learner's browser. A malicious frontend can still
read and exfiltrate that origin-local data on a future visit. Nginx, Cloudflare and
application logs can contain IP addresses, user agents, paths and request IDs and
must be treated as potentially personal data.

Worst-case compromise means an attacker can alter questions or serve malicious
JavaScript to every visitor, steal origin-local learner data, access request logs,
destroy availability and use host or control-plane credentials to attack adjacent
systems. Database disclosure currently exposes the complete question bank and
schema, not browser-local progress. Host or GitHub credential compromise has the
larger blast radius.

A defensible annual loss expectancy is not available: incident frequency, revenue
impact, response cost and contractual exposure have not been quantified. Do not
invent an amount. Record those inputs before making a vendor or insurance decision.

## Threat model and severity

The top three STRIDE risks by likelihood multiplied by impact are:

1. **Tampering / elevation of privilege — high.** A stolen GitHub or host credential
   can publish malicious frontend code, replace backend behavior or weaken release
   controls.
2. **Information disclosure — high.** A host, browser-origin or future backup
   compromise can expose logs, operator secrets, database contents or learner-local
   notes and progress.
3. **Denial of service — medium.** Destructive host access, dependency compromise,
   resource exhaustion or failed recovery can make both origins unavailable.

Use these severities:

- **SEV-1:** confirmed active compromise, malicious production code, exposed active
  credential, unauthorized database/log access or widespread client-side data risk.
- **SEV-2:** credible exploit with uncertain exposure, integrity loss, repeated
  security-control failure or prolonged unavailability without confirmed compromise.
- **SEV-3:** contained scanner/report finding with no evidence of production access.

When evidence is incomplete, start at the higher severity and downgrade only after
recording why.

## Detection and escalation

Logs alone are evidence, not detection. A signal is effective only when a named
person receives and acknowledges it.

| Signal | Intended detection target | Response target |
| --- | --- | --- |
| Required PR checks, CodeQL and secret scanning | unsafe change, code weakness or committed credential | block merge; triage the same day |
| Manual dependency audit | known Python or Node advisory at review time | operator-initiated; no unattended notification target |
| Manual production smoke + deduplicated GitHub issue | release mismatch, answer leak, broken isolation, headers or availability | after deployment or during incident response; no continuous external MTTD claim |
| Hourly local recovery attestation consumed by manual smoke | missing/corrupt/stale local backup, stale full-job success marker, missed restore or failed/stopped health-marker publisher | local machine signal on the next hourly run after its age threshold; external verification is operator-initiated |
| Hourly analytics-retention success attestation | missed/failed applied retention, stale marker, unsafe owner/mode or broken reader ACL | local machine signal on the next hourly run after the 26-hour threshold; external verification is manual |
| Hourly release-staging inventory via the public recovery attestation | unsafe or more-than-two-hour-old frontend/static/SEO staging | local machine signal within roughly 3 hours of creation; external verification is manual |
| Hourly finalized-release snapshot inventory via the public recovery attestation | more than 10 frontend rollback/external snapshots, more than 512 MiB allocated per location, or an unsafe reserved-prefix tree | local machine signal on the next hourly run; external verification is manual |
| Hourly pre-deploy-backup temporary inventory via the public recovery attestation | unsafe or more-than-two-hour-old partial dump/legacy stderr residue | local machine signal within roughly 3 hours of creation; external verification is manual |
| GitHub private vulnerability report | researcher-reported weakness | acknowledge within two business days |
| Cloudflare, Nginx, application and system journals | traffic or runtime anomaly | evidence only until an alert rule pages the owner |

The GitHub issue path was technically exercised on 2026-10-13: a real production
contract passed before a synthetic failure opened issue #62, and a subsequent full
success closed it. Delivery into the owner's human-controlled email or mobile
channel and acknowledgement have not been confirmed, so guaranteed human MTTD
remains **unbounded**. Before claiming a human MTTD, configure a named responder,
confirm that delivery path and record the acknowledgement time. The public recovery
attestation detects ordinary backup/restore/publisher failure but can be forged by a
fully compromised host. The offsite path has additional blocked alert gates in
`docs/OFFSITE_BACKUP_RUNBOOK.md`.

Anyone who sees a SEV-1 signal starts this runbook immediately. For SEV-2/3, open a
private GitHub advisory or private incident record; never place exploit details,
secrets, personal data or raw logs in a public issue.

## First 15 minutes

1. Record the awareness time in UTC, reporter, affected surface, observed indicators
   and current severity. Assign an incident lead and a separate recorder when
   another trusted person is available.
2. Use a known-clean device and network for account recovery and credential
   rotation. Do not trust the suspected host to change secrets that protect it.
3. Preserve evidence before destructive action: GitHub event/check identifiers,
   webhook delivery IDs, Cloudflare events, relevant journals and logs, container
   image IDs/digests, deployed release headers and database/backup checksums. Store
   evidence encrypted with mode `0600` or stricter outside public repository paths.
   Container inspection can contain environment secrets; never paste it into an
   issue or chat.
4. Stop further harm at the narrowest trustworthy boundary. Disable a compromised
   GitHub token or webhook, block public ingress at Cloudflare/Nginx, or stop the
   backend before changing data. Do not delete containers, logs, commits or backups.
5. Start a credential inventory. Treat every secret readable by the compromised
   identity as exposed, even if logs do not show its use.

## Containment playbooks

### GitHub, workflow or release compromise

1. Revoke suspicious sessions, tokens and app authorizations from a clean device.
   Preserve identifiers and timestamps, not token values.
2. Keep the generic PCEP deployment webhook disabled. If it was re-enabled, disable
   it before investigating. Disable Actions temporarily if workflow execution itself
   is untrusted.
3. Record branch-protection, Actions-permission and security-setting JSON before
   correcting drift. Preserve the suspicious commit and workflow run; do not rewrite
   history during the evidence phase.
4. Compare `main`, the deployed frontend marker and `X-PCEP-Release` against the last
   known-good reviewed commits. Treat a valid Git signature or green CI as evidence,
   not proof, when the controlling identity may be compromised.
5. Roll back through `docs/OPERATIONS.md`. Never run plain `docker compose pull/up`,
   deploy from an unreviewed worktree or bypass the backup/image-scan gates.
6. Rotate the webhook secret and every host credential accessible to the compromised
   GitHub identity. Re-enable Actions only after workflow sources, action SHAs,
   permissions and required checks are verified.

### Leaked credential or committed secret

1. Revoke or rotate first; deleting a line or commit does not invalidate a secret.
2. Identify its permissions, creation/last-use evidence, every host and vendor where
   it was stored, and the first possible exposure time.
3. Search tracked files and all reachable history with `make audit-secrets`. Review
   GitHub secret-scanning alerts and provider audit events without exposing values.
4. Replace dependent services and invalidate sessions where relevant. Rotate Django,
   application-database and database-administrator credentials independently; keep
   the administrator secret out of the backend environment.
5. Purge history only after rotation and through a separately reviewed coordinated
   procedure. Assume forks and caches retain the original value.

### Host or container compromise

1. Block public ingress and stop application writes. Isolate the host through the
   hosting provider or firewall; do not reboot until volatile-evidence value is
   considered.
2. Preserve provider events, system journals, Nginx/Cloudflare logs, process and
   socket listings, container/image metadata and hashes of relevant files. Raw
   captures are sensitive incident evidence.
3. Snapshot only for investigation; do not promote a suspect container or disk image
   into a trusted rollback artifact.
4. Rebuild from reviewed sources on clean infrastructure. Restore data only from a
   checksum-verified backup that passes the isolated restore drill.
5. Rotate GitHub, Cloudflare/tunnel, webhook, Django, database and offsite-backup
   credentials that the host could read. Validate adjacent services separately.

### Database disclosure or integrity loss

1. Stop the backend to end application sessions and writes. Preserve a private,
   checksummed logical dump when doing so will not expand exposure.
2. Record counts for users, sessions, questions, choices and unexpected role/object
   ownership without exporting row contents into the incident log.
3. Revoke affected logins and rotate application and administrator passwords. The
   migration role must return to `NOLOGIN` with no password.
4. Restore the newest trusted backup into a network-isolated disposable database,
   never over production during investigation. Compare schema, ownership, migrations
   and question invariants.
5. Rebuild production and re-run the exact role-posture verifier, migration check,
   question audit and public smoke contract before allowing traffic.

### Stale or failed daily-backup job

1. Preserve the backup and operations-health journals, the private success-marker
   metadata and contents, the newest dump/checksum metadata, free space and relevant
   filesystem/kernel events. Never hand-edit or refresh the marker.
2. Distinguish dump/checksum failure from a later retention, final-inventory or
   marker-publication failure. A fresh dump alone does not prove that the complete
   scheduled job succeeded; the prior marker must remain authoritative.
3. Verify every complete retained checksum read-only. Preserve an unpaired dump or
   sidecar as possible crash evidence; never use a wildcard or broad age-based
   cleanup. Treat unsafe type, owner, mode or unexplained content failure as a
   storage or host-integrity incident.
4. After fixing the specific failure, start the reviewed backup service once. Require
   a successful unit result, a newly written private marker, healthy operations
   publication and an isolated restore before closure.
5. If personal data may have been lost, exposed or made unrecoverable, start the
   documented breach assessment and applicable GDPR Article 33 72-hour decision
   clock; backup recovery work does not pause that clock.

### Stale or failed analytics retention

1. Preserve the analytics-retention and operations-health journals, marker metadata
   and ACLs, the configured website identity/domain and database audit evidence. Do
   not export event/session rows or the database URL into an issue or chat.
2. Treat a missing, wrongly owned, public, malformed or inexplicably replaced marker
   as possible host/control tampering. A dry-run cannot refresh success and must not
   be reclassified as an applied retention run.
3. Preview the exact PCEP-scoped transaction through the documented transient unit.
   Confirm the configured UUID/domain and deletion counts before any retry with
   `--apply`; never issue broad manual table deletes as alert cleanup.
4. After the reviewed applied service succeeds, require a new `umami`-owned marker
   with no group/other ACL access except the exact named read-only `micu` entry, the
   exact traverse-only directory ACL, healthy operations publication and the public
   smoke contract before closure.
5. Determine the earliest missed retention date and whether data exceeded the
   published 180-day period. Record the controller decision, data-subject impact and
   any required response; start the GDPR Article 33 72-hour assessment if the facts
   also indicate a personal-data breach.

### Isolated restore-check readiness failure

1. Preserve the restore-check and operations-health journals, immutable image ID,
   newest backup/checksum names, exact failure time and disposable-container
   ownership metadata. Never rerun against the live database.
2. Distinguish an initialization race from corruption: `database system is starting
   up` immediately after container creation can be transient, while checksum,
   decompression, SQL, ownership or invariant failures remain recovery incidents.
3. Confirm no disposable container remains. If one exists, require the exact
   ownership token, image and immutable container ID before removal; never delete a
   same-named foreign container.
4. Rerun the reviewed networkless drill once. Close the alert only after the full
   restore, invariant validation, private success marker, operations health and
   external public contract all pass.
5. Escalate a repeated startup timeout or any restore/invariant failure as a
   database/image/storage incident; do not normalize it as a readiness race.

### Malicious frontend or browser-origin incident

1. Block or replace the learner origin and purge CDN caches. A service worker can
   keep a compromised asset alive after the server is fixed, so verify the release
   marker from a clean browser and a cache-bypassed request.
2. Restore a known-good static release through the atomic publisher and verify that
   the learner and runner remain separate origins with their reviewed CSPs.
3. Determine whether code could read/export learner-local progress or notes. If so,
   tell affected users what local data was at risk and how to clear site data; do not
   imply the server held that data.
4. Review third-party build inputs, pinned action commits, npm integrity/signatures
   and Pyodide hashes before republishing.

### Stale publication staging or release-disk growth

1. Preserve the operations-health journal, publisher/service journal, exact directory
   metadata, filesystem/kernel events and free-space measurements. Do not copy file
   contents into a public issue.
2. Confirm whether a publisher process and its reviewed non-blocking lock are active.
   A fresh legitimate staging tree is allowed for two hours; never delete a tree
   while its publisher may still own it.
3. Validate the live release, the immediate rollback and the external backup before
   changing the stale path. Inventory only exact `.frontend.release-*`,
   `.static.release-*` and `.seo.release-*` candidates; do not use a broad wildcard
   delete and never target `frontend`, `static` or `seo` themselves.
4. If no publisher owns an exact stale candidate, preserve any evidence needed for
   a storage/process investigation and use a separately reviewed exact-path cleanup.
   Recheck free space, rerun the relevant publisher only from a verified source and
   start operations health again.
5. Escalate repeated residues, unsafe ownership/mode, future timestamps or I/O errors
   as a possible host/storage incident. Follow the host-compromise playbook if the
   metadata cannot be explained by a failed reviewed publication.

### Operations-health marker publication failure

1. Preserve the failed unit journal, the existing marker metadata and ACL, relevant
   filesystem/kernel events and the exact primary plus cleanup diagnostics. Do not
   republish a hand-written `ok` marker.
2. Confirm the existing public marker still has only `schema`, `status` and
   `checked_at`; treat it as stale evidence, not current health. Never copy its
   private journal diagnosis into the public file or an alert issue.
3. Inventory only exact `.status.json.partial-*` entries in the private state
   directory. Do not remove the state directory or its last published marker, and
   preserve a partial when storage failure or host compromise is under investigation.
4. Fix the initiating verifier/write/storage failure first, verify the installed
   unit and directory ownership/mode, start the reviewed service, then confirm the
   external no-store endpoint and full production smoke contract.
5. Escalate repeated write, unlink or directory-`fsync` failures as a storage/host
   incident and evaluate every credential readable by that host identity.

### Excessive or unsafe finalized release snapshots

1. Preserve the operations-health and publisher/retention journals, exact parent and
   candidate metadata, free-space measurements and the current non-blocking lock
   state. The public marker intentionally contains no names, counts or sizes.
2. Inventory only direct exact `.frontend.previous-<UTC-basic>-<8 lowercase hex>`
   and `frontend.<UTC-basic>-<8 lowercase hex>` children. Treat a malformed reserved-
   prefix name, symlink, special entry, wrong owner or world-writable descendant as
   possible tampering; never traverse or normalize it merely to make health green.
3. Validate the live frontend plus at least two complete rollback and backup copies.
   Keep legacy `frontend.bak.*`, static/SEO copies, database dumps and unrelated
   artifacts outside this incident's deletion scope.
4. Run `make release-retention` in its default preview mode. Review every exact path,
   validation result and allocated-space total, then apply only that reviewed plan
   when no publisher/retention process owns the lock. Never use a wildcard, recursive
   parent cleanup or filesystem age alone.
5. Recheck free space, rerun operations health and the full public smoke contract,
   and retain the evidence. Escalate unexplained unsafe metadata, repeated growth or
   I/O failure to the host-compromise playbook.

### Stale pre-deploy backup temporary

1. Preserve the deployment and operations-health journals, exact entry metadata,
   filesystem/kernel events, free-space measurements and maintenance-lock state.
   Never publish or attach dump/error contents to a GitHub issue.
2. Inventory only exact `.sql.gz.partial-<32 lowercase hex>` and legacy
   `.sql.gz.stderr-<32 lowercase hex>` matches directly under the private deployment
   backup root. Reject a symlink, non-regular entry, unsafe mode/owner, malformed
   timestamp or future time as possible tampering; do not traverse it.
3. Confirm whether the reviewed backend deployment or role-separation operation is
   still running and owns the maintenance lock. A valid temporary younger than two
   hours is allowed; never remove it from under an active operation.
4. If no operation owns an exact stale path, preserve any evidence required for a
   storage/host investigation, verify the latest complete backup and isolated
   restore, then use a separately reviewed exact-path cleanup and re-run operations
   health. Never use a broad wildcard or delete a completed dump as cleanup.
5. Treat repeated residues, cleanup `fsync` failures or unexpected stderr growth as
   a storage/host incident. Review database-container integrity and every credential
   available to the deployment identity before retrying deployment.

### Pre-deploy backup retention refusal

1. Stop backend deployment before build or cutover and preserve the exact retention
   output, matching-file metadata, filesystem/kernel events and maintenance-lock
   state. Do not rename, chmod, decompress or delete a suspect match in place.
2. Inventory only direct children matching current
   `pcep_db_<UTC-basic>.sql.gz`. Legacy timestamps, named intervention dumps, the
   `daily/` tree and configuration/frontend artifacts are out of scope even when
   they are old.
3. Treat a symlink, wrong owner/mode, future timestamp, gzip/header failure or
   identity change as possible storage tampering until explained. Verify a recent
   daily checksum and isolated restore before considering cleanup.
4. Run `make predeploy-backup-retention` without apply and review every exact path
   and SHA-256. Use the reviewed `--apply` path only after evidence preservation;
   never use a wildcard, recursive removal or an unreviewed filesystem-age rule.
5. After partial apply or directory-`fsync` failure, repeat discovery from disk. The
   command removes oldest first and flushes each unlink, but the journal/output is
   not authoritative over the current directory. Escalate repeated failure as a
   host/storage incident.

### Automatic rollback-image retention refusal

1. Stop the deploy before database backup, build or cutover and preserve its private
   output, `docker events`, the exact rollback tag-to-image-ID inventory, container
   inventory and shared-lock state. Do not run a host-wide prune.
2. Scope review only to exact `pcep-backend-rollback:<UTC-basic>-release-<release>`
   tags. Candidate/review repositories, PostgreSQL, build cache and other host
   applications are outside this control.
3. Treat invalid metadata, a changed tag identity, embedded runtime-secret names or
   an unexpected in-use image as possible tampering. Preserve the tag and follow the
   host-compromise playbook when it cannot be explained.
4. Run `make backend-image-retention` without apply, vulnerability-scan and exercise
   the intended retained rollback IDs, then use the explicit reviewed `--apply` path
   only if every selected tag is understood. Never force-remove an image or bypass
   the maintenance lock.
5. Retry deployment only after the preview selects at most its normal one-in/one-out
   change and all exact tags validate. Verify the live backend release and external
   smoke before closure.

## Recovery gates

Do not close or downgrade the incident until all applicable gates pass:

- root cause and earliest possible exposure time are recorded;
- compromised credentials are revoked and replacements use least privilege;
- the remediation has a reviewed PR with every required check green;
- backend/database images and dependencies pass the blocking audits;
- database ownership, grants, migrations and question invariants are exact;
- frontend/backend release identities, runner isolation and the public smoke contract
  pass from outside the host;
- backups and an isolated restore are verified without overwriting evidence;
- Cloudflare/CDN caches and service-worker behavior are checked where relevant;
- monitoring is watched for at least 24 hours after a SEV-1 recovery;
- follow-up owners and dates are recorded, including any notification decision.

## Regulatory and communications record

Record when the organization became aware of a possible personal-data breach. If a
breach is likely to risk individuals, GDPR Article 33 can require notification to
the supervisory authority within 72 hours of awareness; affected-person notice and
other national, contractual or vendor duties require case-specific legal review.
Document the facts, risk assessment, decision and approver even when notification is
not required. Do not claim SOC 2, ISO 27001, HIPAA or payment-card scope without a
separate assessment.

Use this internal update shape:

```text
UTC time / severity / incident lead
Known facts and evidence references
Affected and explicitly unaffected systems/data
Containment completed and next safe action
Credential rotations and notification clock status
Next update time
```

Public communication must state verified facts, affected time window and data,
actions users should take, remediation status and a contact channel. Never speculate,
expose indicators that enable exploitation or promise that no data was accessed when
logs cannot establish that.

## Vendors, access and remaining gates

- **GitHub:** source, CI and security reporting. The owner had 2FA enabled on
  2026-10-08; the repository had no deploy keys, Actions secrets, variables or
  self-hosted runners. Recheck during an incident. Replace the broad host CLI
  credential with a task-scoped, expiring credential through an out-of-band account
  session; never automate token creation or print its value.
- **Cloudflare:** public proxy/tunnel and a possible future R2 provider. Account MFA,
  recovery, audit-log retention, DPA and subprocessor review require owner evidence.
- **Hosting provider:** identity, support escalation, snapshot isolation, account MFA
  and DPA are not documented in this repository and must be recorded privately.
- **Let's Encrypt and package registries:** certificate and build-time supply-chain
  dependencies. Preserve certificate/account events and package provenance during
  relevant incidents.
- **Offsite storage:** not active and must remain blocked until every gate in the
  dedicated runbook passes.

The primary unresolved response risks are the untested human notification path,
missing human tabletop, broad host GitHub credential and undocumented provider/DPA
evidence. They require account-owner decisions or external services and cannot be
truthfully closed by a code change.

## Tabletop checklist

Run at least twice a year and after control-plane changes. Use synthetic evidence;
never rotate production secrets merely to simulate an incident.

1. Pick one scenario: malicious `main` release, active token leak, host compromise,
   database tampering, failed backup after dump publication, stale analytics
   retention, restore-readiness race,
   stale publication staging, stale
   pre-deploy backup temporary, excessive/unsafe finalized snapshots, rollback-image
   retention refusal, retention target replacement, failed health-marker cleanup,
   incomplete host reboot recovery or malicious service worker.
2. Name the incident lead, recorder and notification recipient.
3. Measure time to receive the alert, acknowledge, identify releases and choose the
   containment boundary.
4. Walk through evidence preservation, credential scope, rollback/restore and public
   validation without performing destructive production steps.
5. Exercise the 72-hour decision record and draft a user update from verified facts.
6. Record date, participants, measured times, failed assumptions and remediation
   owners. Update this runbook and repeat any failed step.
