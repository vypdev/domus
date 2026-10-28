# Proposed setup and operations guide

This guide describes intended operation. No Domus artifact is installed or deployed yet.

## Recommended setup

Choose Supervisor App/Ingress or standalone Container. Both ship in the first usable release.
Choose Stable for production or isolated Edge for experimental validation. Create one household and time zone,
then link each participating member to their own verified HA account and assign explicit Domus roles.
Optional person associations supply profile/presence data only.

Supervisor stores Domus data in its own persistent application namespace and exposes the UI through Ingress.
Standalone uses a private host binding, authenticated access and an owned volume, connecting to HA Core
without assuming Supervisor services. No direct browser identity headers establish trust.
Validate the chosen target's authentication, persistence and native HA integration before declaring setup complete.

## Permissions and configuration

Administrators manage membership, point policies, verification, corrections and automation grants.
Collaborative points policy is configured in the application. The preview discloses base points, rounding/precision, performer shares and actual total; only an authorized configuration change selects a different policy. Existing awards retain their snapshots, and reopening reverses the amounts actually awarded. Restricted performers need adult approval by default, while adults do not.
Adults perform authorized household commands; restricted and viewer roles use the reviewed permission matrix.
Technical HA commands use explicit grants without impersonating members. Domain forms do not accept tokens.
Optional product lookup is configured through a bounded provider adapter; no external catalog is mandatory. Keep camera frames, household identity and stock history local. Provider failure leaves camera/manual entry and local catalog search usable.
Invalid or unknown configuration versions block the affected operation and preserve prior settings.

## Recovery

| Symptom | Retained fact | Next action |
|---|---|---|
| Lost save response | Operation may already be committed | Look up the operation or replay its original idempotency key |
| Stale task or stock revision | Latest backend record is intact | Review current state before deliberate resubmission |
| Receipt saved, stock missing | Physical receipt is recorded; posting is pending | Retry only the identified stock post |
| HA unavailable | Domain records persist; native projections may be stale | Restore HA connectivity and reconcile projections |
| Schema too new | Database remains intact; writes are blocked | Use a compatible application or restore the paired backup |
| Insufficient role | No denied command effect was committed | Ask an administrator to review access |

Backoff is bounded. Repeated availability failures become an actionable status rather than endless notifications.
Logs use safe error codes and correlation IDs; exported diagnostics exclude credentials and unnecessary household details.

## Backup, upgrade and rollback

Back up the consistent database, required media, schema manifest and installation configuration.
Encrypt sensitive backup material and retain local ownership. Verify backup integrity in an isolated restore.
Stable and Edge never share credentials, DB volumes or household mutations. Restoring a copy into Edge
requires an explicit import/sanitization operation; it must not retain production service credentials.
Schema-incompatible downgrade requires the paired data backup; never run old code against newer schemas blindly.

## Authorized local dogfooding

The owner permits Google Chrome at http://homeassistant.local:8123/.
Before mutation, identify the Domus channel/artifact and create records with a unique domus-dogfood run label.
Track each created ID and any ledger compensation. Exercise normal, denied, replay, offline, partial and recovery paths.
Clean only recorded test-owned artifacts through supported domain operations. Do not bulk-clear native shopping lists,
delete real household records, change gateway policy, install/promote production, or expose secrets in evidence.
Record retained fixtures if a cleanup fails; no clean-state claim is made until reconciled.
This authorization enables controlled functional use, not an unrelated production deployment.
