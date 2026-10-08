# Security incident response runbook

Status: **active**, with notification and tabletop gaps recorded below.

Owner: repository owner and production server operator. If one person holds both
roles, keep a timestamped incident log and ask an independent trusted person to
review containment and recovery decisions before restoring service.

Last technical review: 2026-10-08. Last human tabletop: **not completed**. Review
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
| Daily dependency audit | newly published Python or Node advisory | under 24 hours after the scheduled run |
| Six-hour production smoke | release mismatch, answer leak, broken isolation, headers or availability | under 6 hours plus notification latency |
| Daily backup and weekly restore services | missing/corrupt local recovery point | investigate before the next scheduled backup |
| GitHub private vulnerability report | researcher-reported weakness | acknowledge within two business days |
| Cloudflare, Nginx, application and system journals | traffic or runtime anomaly | evidence only until an alert rule pages the owner |

GitHub notification delivery and an independent production/backup pager have not
been end-to-end tested. Current guaranteed MTTD is therefore **unbounded** despite
the scheduled checks. Before claiming an MTTD, configure a named responder, test a
real failure notification and record the date, delivery path and acknowledgement
time. The offsite path has additional blocked alert gates in
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
   database tampering or malicious service worker.
2. Name the incident lead, recorder and notification recipient.
3. Measure time to receive the alert, acknowledge, identify releases and choose the
   containment boundary.
4. Walk through evidence preservation, credential scope, rollback/restore and public
   validation without performing destructive production steps.
5. Exercise the 72-hour decision record and draft a user update from verified facts.
6. Record date, participants, measured times, failed assumptions and remediation
   owners. Update this runbook and repeat any failed step.
