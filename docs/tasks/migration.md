# Task storage migration and compatibility

The development source uses SQLite schema 8 for fixed recurrence storage. The installed immutable
Edge.5 package uses schema 7; retained Edge.3 remains the separately pinned M1 schema-4 package.
Current source tests do not upgrade those installations or establish a released package upgrade.
Keep the exact application/data pair and installation/channel identity.

| Schema | Added task state | Preservation |
|---|---|---|
| 1–4 | Existing identity, household commands, recovery and retained history | Original versioned identity/replay facts remain authoritative |
| 5 | Task policy, definitions, occurrences and completion cycles with scoped constraints | Existing household/member/history rows are retained |
| 6 | Frozen material bindings, usage intents, strict codecs and compare-and-set guards | Legacy task/request evidence remains readable; original hashes/receipts stay unchanged |
| 7 | Three causal-evidence indexes on the existing outbox | No business table, task row, receipt or event is rewritten |
| 8 | Scoped recurrence rules, matching durable progress and immutable nominal slots | Original task, receipt, audit, outbox and historical records remain authoritative |

Initialization accepts an empty owned destination or supported versions 1–7, verifies the application
marker and installation/channel, then repeats inspection inside the bounded writer transaction.
Additive DDL, any required legacy-document upgrade and user_version advancement share that transaction.
An unsupported future version, mismatched identity or unrelated database is rejected. Normal runtime
transactions require the current version; a different installation is never invented to adopt data.

The schema-7 indexes are task_cycle_event_page, task_occurrence_event_page and
task_dependency_ack_page. They support projection of original live completion/reopening/acceptance
facts; they are not a second review or stock ledger. Restored-away operations remain historical.

## Before an upgrade

1. Identify the exact source/package and persisted installation UUID/channel. Stable and Edge have
   separate data; native and standalone do not change that ownership boundary.
2. Create and independently inspect a [manual snapshot](../snapshots.md) with the compatible runtime.
   Keep the complete private bundle and the compatible application needed to recover it.
3. Verify migration and restoration against disposable copies before adopting a new package. Stop
   the runtime for offline activation. This source checkpoint does not publish a new Edge image.

Never edit user_version, rewrite receipts, clear an outbox or regenerate identifiers as an upgrade
shortcut. A failed migration retains the original version and rolls back its additions. Review the
reported error and exact owned destination before retrying initialization deliberately.

## Restoring an older checkpoint

Preparation retains original checkpoint bytes. Inspection can validate supported historical schema
inputs without migrating them. Offline activation upgrades only its prepared target, imports verified
later operation evidence and selects a new generation after validation. It does not migrate the source
database or original snapshot in place. Interrupted activation uses the same ID and source binding.
See [restoration](../restoration.md) for the console protocol and uncertainty handling.

A selected historical business state may omit a later completion, material correction or manager
acceptance. Its retained receipt proves that operation was processed before restoration; it does not
apply the effect again. Queries distinguish current facts and historical outcomes. Current authority
is still required to recover a result. Old material/approval evidence never becomes a current grant.

Rollback requires a compatible application/data pair. A schema-7 runtime must refuse schema 8.
To reverse a restore, prepare from its retained source-checkpoint against
the latest selected source and activate a new verified restore ID; do not reverse the pointer manually.

## Source evidence and limits

Frozen SQL fixtures for versions 1–7 come from their original runtime checkpoints. In particular,
the v6 input comes from immutable 7beb63c and includes a reopened prerequisite, completed dependent
work, an approved closed cycle, confirmed material correction and restored-away settlement. The
schema-7 tests retain every original table row and prove failed index DDL rolls back exact database
bytes. Actual old-checkpoint inspection/activation tests preserve input/source bytes and upgrade
only the prepared target.

The genuine schema-7 fixture was created under source 64908ee before recurrence DDL changes. It
contains a household, members, a completed task/cycle and original operation evidence. Its SHA-256
is c5ca7b2383e9f75561a59b9ea0bbbd98736ae400b19e735b5a6fdf90ca139ea5. Existing fixtures are unchanged.
Schema-8 tests reject ordinary schema-7 read/write transactions before explicit initialization,
retain original receipts during migration, and roll back new DDL plus version advancement after
injected failures. Rule, matching pattern progress and exact slot command proof use deferred
constraints within the same transaction. Snapshot inspection also checks the new documents,
headers, installation identity, cursor binding and original effect references.

The current-source CI image builds the checked-out backend and frontend for both architectures.
The immutable Edge.5 image supplies real schema-7 upgrade and refusal controls; CI does not move
its source pin or publish an owner package. Actual hosted image results remain a separate required
gate. See [storage evidence](../evidence/recurrence-storage.json) for the current measured scope.

Those observations are retained in [task evidence](../evidence/task-execution-foundation.json).
They are distinct from image/cross-architecture adoption, real consumer ledgers and a restoration on
the owner's HA, which remain required before integrated release claims. No automatic backup schedule
or retention policy is introduced. The [operator guide](operator-recovery.md) covers current task
outcomes, original-command recovery and pending material/consumer states.
