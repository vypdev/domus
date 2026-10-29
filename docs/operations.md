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

Task completion reviews adjustable actual materials in the same submission by default, with a per-task separate-recording option. A stock shortfall saves performed work and a pending-regularization intent without a stock movement. Review its source and actual inventory facts before authorized settlement; restocking alone does not post the old usage. Reopening does not return materials automatically. Reversal of already-spent points can create a factual negative balance; retain delivered rewards and block new redemption until sufficient unreserved points exist.
Adults perform authorized household commands; restricted and viewer roles use the reviewed permission matrix.
Technical HA commands use explicit grants without impersonating members. Domain forms do not accept tokens.
Optional product lookup is configured through a bounded provider adapter; no external catalog is mandatory. Keep camera frames, household identity and stock history local. Provider failure leaves camera/manual entry and local catalog search usable.
Invalid or unknown configuration versions block the affected operation and preserve prior settings.

Administrator mapping defaults to all_ha_administrators; setup_administrator and selected_ha_user are explicit alternatives. Verify current HA identity/administrator status through the reviewed adapter, retain grant provenance and revoke invalid inherited grants. Household role profiles and member exceptions are configurable through current administrator authority; known suspension and hard domain constraints remain enforced. Changing a mapping or profile through Domus cannot remove its last active effective administrator. External HA account loss requires the reviewed authenticated recovery procedure, never a browser-order fallback.

Reopening a prerequisite preserves already-completed downstream work and points and raises dependency_attention. Approved unfulfilled redemptions without backing enter funding_hold with approval/reservation retained; delivery cannot proceed until funding is sufficient or an explicit authorized resolution occurs. Disabling a rule fences new admissions and subsequent steps while recording the result of already-started atomic commands. Restart/re-enable does not silently resume its cancelled queue or waits.

## Recovery

| Symptom | Retained fact | Next action |
|---|---|---|
| Lost save response | Operation may already be committed | Look up the operation or replay its original idempotency key |
| Stale task or stock revision | Latest backend record is intact | Review current state before deliberate resubmission |
| Receipt saved, stock missing | Physical receipt is recorded; posting is pending | Retry only the identified stock post |
| Task saved, material stock insufficient | Work completion and pending material intent persist; no negative stock was invented | Review actual inventory facts and explicitly resolve the retained intent |
| Negative points after reopening | Actual reversal and delivered reward remain recorded | Earn points to cover the deficit; new redemption requires sufficient unreserved credit |
| Completed work has dependency attention | Real downstream completion, points and material facts persist | Review the linked reopened prerequisite; do not cascade reopening automatically |
| Approved reward has a funding hold | Approval and reservation persist; delivery has not occurred | Recover sufficient credit or explicitly review/cancel; do not bypass affordability |
| Rule disabled with a settling command | New work is fenced; the started command's actual result remains | Inspect the retained receipt; do not resume cancelled waits on re-enable |
| HA unavailable | Domain records persist; native projections may be stale | Restore HA connectivity and reconcile projections |
| Schema too new | Database remains intact; writes are blocked | Use a compatible application or restore the paired backup |
| Insufficient role | No denied command effect was committed | Ask an administrator to review access |

Backoff is bounded. Repeated availability failures become an actionable status rather than endless notifications.
Routine activity/log retention never deletes the command guards needed to prevent duplicate effects. Receipt access remains subject to current permissions, including after suspension.
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
