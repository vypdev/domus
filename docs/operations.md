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

## Inventory catalog and movement history

The protected Inventory workspace uses the current household session. Reads
require household access, and registration and intake require a current
`inventory.manage` grant. New products receive a binding at the household's
logical Pantry location. Intake posts an attributable movement, audit entry and
original-command receipt in one SQLite transaction. The existing task material
authority continues to govern linked consumption.

Schema 20 adds the catalog to schema 19. Migration keeps existing material
bindings, locations, reservations and movements at their existing identities.
Legacy task material references remain usable through their original task
flows. A compatible snapshot verifies that each new product resolves its
original Pantry binding and that stock reconciles with movements and reservations.
Restore activation keeps the original request identity and distinguishes effects
present in the current database from historical receipts. Downgrade requires a
compatible database and image pair.

Schema 21 adds movement kinds and a product history index to the same ledger.
It preserves movement positions, IDs, links, balances, reservations, and
operation receipts from schema 20. It classifies historical rows using their
existing posting and correction references. Upgrade runs in one SQLite
transaction. A compatible restore verifies exact ledger balance and linked
compensation before activating the generation.

The history requires current household read access. Pagination is newest append
first with a signed cursor scoped to the product, current member, authorization
context and page size. Adjustments and intake reversals require
`inventory.manage` and a reason. The writer checks the projected balance and
active reservations before appending a movement and committing its original
receipt. A unique correction link allows one full reversal per intake.

## Pantry replenishment

Schema 22 adds one revisioned minimum and target policy per Pantry product.
Existing products start with both thresholds at zero. The upgrade preserves
product identities, movement links, reservations, task effects and original
operation receipts. Snapshot validation checks the policy table and verifies
whole-piece precision before a compatible restoration can activate.

Current `inventory.manage` is required to edit thresholds or recover their
original write receipt. The write checks the expected revision and commits
the policy, audit entry and receipt in the same transaction. Inventory reads
the policy, ledger balance and active reservations in one snapshot. Its
replenishment source is the Pantry product identity. The projected amount is
target minus availability when below the minimum, and zero otherwise. These
reads create no movements or task effects. Restocking leaves any pending task
consumption available for separate review in Tasks.

## Shared shopping list

Schema 24 adds household-scoped manual extra records to schema 23. It preserves
the Pantry ledger, replenishment policies, task reservations, purchases,
physical receipts and original operations. A manager's clear stores the member
and time in the original record. Snapshot verification checks each extra's
product binding, base unit and quantity precision.

List and source reads use one transaction. Apply each task's own reservation,
then allocate unreserved stock once in occurrence and material-line ID order.
Compatible incoming purchases cover Pantry first and then uncovered task
materials. Manual extras add independently. Only current task readers receive
Task sources or quantities. Add and clear use current `shopping.request` and
`shopping.manage` respectively, including original receipt recovery.

An original receipt may be historical after restore. If an extra is active
again in the restored list, a manager can clear it with a new request after
reviewing that state. Replaying the historical clear returns its archived
receipt.

## Purchase sessions

Schema 25 adds session headers and ordered links to existing purchase rows.
Migration from schema 24 keeps individual purchase and receipt history, the
Pantry ledger and shared-list extras. The session and every item commit with one
original operation receipt. A failure during recording rolls back the entire
trip. Snapshot checks verify the item count and the session's actor and time
against its items.

Recording and original-command recovery require current `shopping.manage`.
Session history and details require `household.read`. Each item's physical
receipts and Pantry postings continue as independent operations. A restored
historical session receipt preserves its original identifiers. Review the
current history before recording a new trip.

## Shopping purchases and receipts

Schema 23 adds household-scoped purchase and physical receipt tables to schema
22. Migration preserves Pantry stock, replenishment policies, reservations and
previous operation receipts. Snapshot verification reconciles purchase totals
and revisions with receipt rows and checks each posting against its attributed
Inventory movement and stable receipt source.

Current `shopping.manage` is required to record purchases and physical
receipts. Current `inventory.manage` is required to post tracked receipts.
Recovery applies the permission for the original action. A physical receipt
commits with the purchase revision and its operation receipt. Posting commits
the stock movement, receipt link, purchase totals and original operation in a
separate transaction. A failed posting leaves the received quantity pending.

Restore activation keeps historical operation receipts distinguishable from
effects in the restored database. If an earlier posting is historical and
the restored physical receipt is pending, review the current record before
starting a new posting. A normal Inventory correction remains a separate
ledger fact linked to its original movement.

## Family rewards

Rewards start disabled. A current points administrator can enable new requests,
set offer prices and eligible household roles, and approve or record physical
delivery using a code shared by the requesting member. Existing requests retain
their prices through catalog edits. Disabling rewards pauses new requests while
existing requests remain available for their authorized transitions. The request
history and balances are scoped to the requesting member.

A hold retains the approval and reservation. Confirm the current state before
recording delivery. Cancellation releases an open reservation and retains the
actor and reason. After a lost response, use **Check reward request** to read the
original result or retry the same key. A historical result after restoration
describes the original operation. Review the current request and balance before
starting another change.

Schema 19 adds reward settings, offers, redemptions, funding changes, and the
append-only reward spending records. The migration preserves existing Points
postings. Snapshot inspection verifies funding sources, delivered spending, and
backing. Restore a compatible image and database pair for rollback. See the
[Family qualification](evidence/family-qualification.md) for recovery and image evidence.

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
