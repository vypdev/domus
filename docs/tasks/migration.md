# Task storage migration and compatibility

Current development source uses SQLite schema 14. The historical schema 8 and 9
checkpoints retain their original evidence below. The installed immutable
Edge.5 package uses schema 7; retained Edge.3 remains the separately pinned M1 schema-4 package.
Current source tests do not upgrade those installations or establish a released package upgrade.
Keep the exact application/data pair and installation/channel identity.

| Schema | Added task state | Preservation |
|---|---|---|
| 1–4 | Existing identity, household commands, recovery and retained history | Original versioned identity/replay facts remain authoritative |
| 5 | Task policy, definitions, occurrences and completion cycles with scoped constraints | Existing household/member/history rows are retained |
| 6 | Frozen material bindings, usage intents, strict codecs and compare-and-set guards | Legacy task/request evidence remains readable; original hashes/receipts stay unchanged |
| 7 | Three causal-evidence indexes on the existing outbox | No business table, task row, receipt or event is rewritten |
| 8 | Scoped recurrence rules, matching durable progress, immutable nominal slots and a fair-selection frontier | Original task, receipt, audit, outbox and historical records remain authoritative |
| 9 | Independent member presentation and preferences | Existing member identity and receipts remain intact |
| 10 | Durable relative lifecycle and reviewed scheduling | Existing recurrence and profile facts are retained |
| 11 | Owner-private calendar preferences | Other private settings and original outcomes remain intact |
| 12 | Household materialization horizon | Existing households start at 60 local days; issued work and original receipts are retained |
| 13 | Household repeated-time preference | Existing households use the first appearance. Historical rule and occurrence policies are unchanged |
| 14 | Per-definition overdue recurrence settings | Existing fixed tasks retain all overdue occurrences. Existing receipts and task rows remain intact |

Initialization accepts an empty owned destination or supported versions 1–13, verifies the application
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

Schema 8 is still under development in the unmerged recurrence feature. Its selection frontier is
added before the first schema-8 release; the owner still runs schema 7. Intermediate CI artifacts
remain tied to their exact source/data pair. The genuine
[c5819b8 development input](../../tests/fixtures/sqlite/unreleased-c581-schema8.sql) was generated
before the selection-table addition, with real synthetic rule/materialization receipts. Its SHA-256
is 2f884cd00b735ddf60c567a908bf05e709f887f699953bce7808326e017647b4. Current normal reads,
writes and initialization refuse that unknown development layout and preserve its bytes. This
control does not extend the supported historical migration set or authorize version-number edits.
Keep its matching application for an intentional development rollback.

The later unreleased schema8 refinement adds recurrence_progress_evidence and strict inline original
time evidence. The genuine [b2bcc69 input](../../tests/fixtures/sqlite/unreleased-b2bcc69-schema8.sql)
comes from its actual timed-UNTIL creation, two committed slots and terminal scan under byte-verified
source b2bcc693d6be5065b1be8dc378334199c927735a. Its complete logical fixture SHA-256 is
6c33c79693647e6fed34e693c943012e28ef05a4b153b8901b7e35014105cd63. SQLite iterdump omits
application/schema pragmas; the fixture explicitly restores those actual captured header values.
The first incomplete dump replay exercised version0 and was corrected before the final control.
The original database remains byte-identical, with SHA-256
23f3d880296942c1c732e840e03f95b236d14c275613d1b6d031b9bb314675c8. Current reads, writes and
initialization refuse its previous development layout unchanged. There is no released8 upgrade
claim, version-number downgrade or alteration to any released1..7 input.

Relative storage subsequently refines the unreleased schema8 layout with a closed timing kind on
the shared rule/progress rows, generation relationships that include it, one nonretired timing owner
per definition, and recurrence_relative_slots. Fixed and relative typed writers cannot overwrite
each other's identities. Source-cycle references and original proof retain scoped facts at commit.

The genuine [06b3b9f input](../../tests/fixtures/sqlite/unreleased-06b3b9f-schema8.sql) was captured
before this change with two actual UTC-UNTIL slots and revision-bound original time evidence. All133
original backend module bytes were checked against source06b3b9f38955a25be2511b68b2ea667a84a42d8f.
The complete logical input SHA-256 is aed613d7a6c2718827c05d44cd3fbbdb9d996fce44097f893b5c9bfd4dc28565;
its unchanged raw database SHA-256 is 5d4c4e26e273e7f26e579e728db243c39e29b21dbef53378cdd2368643debe09.
It restores the exact captured application/schema header pragmas omitted by SQLite iterdump. Current
normal reads/writes and initialization refuse its five-table development layout without changing it.
Keep the matching original application/data pair for intentional development rollback; the supported
released source set remains1..7. This adds no released8 migration or automatic retention policy.

Those observations are retained in [task evidence](../evidence/task-execution-foundation.json).
They are distinct from image/cross-architecture adoption, real consumer ledgers and a restoration on
the owner's HA, which remain required before integrated release claims. No automatic backup schedule
or retention policy is introduced. The [operator guide](operator-recovery.md) covers current task
outcomes, original-command recovery and pending material/consumer states.


## Relative lifecycle storage in schema 10

The [genuine schema-9 fixture](../../tests/fixtures/sqlite/v9.sql) is the pre-migration input.
Initialization validates the exact schema-9 layout before adding the inbox and closure ledger.
Existing task, recurrence, profile and operation rows retain their values. A failed migration
rolls back the schema and preserves the source bytes. Ordinary transactions on schema 9 require
explicit initialization.

Keep the complete application and database generation pair for rollback. A schema-9 application
rejects a schema-10 generation. An application that supports schema 10 can restore an older
compatible checkpoint into a new generation and retain original operation and cycle proofs. A
successor that is absent from the selected state stays absent, even when its original closure
remains recoverable.

Schema 13 adds a checked column to the existing household row. The frozen schema-12
input retains the schema and records produced by the previous runtime from the
schema-11 checkpoint. The migration preserves the configured horizon, private
preferences and task evidence. A DDL failure preserves the original schema-12 bytes.

Schema 14 adds a task-scoped settings table with its own revisions and a checked
policy. Existing definitions default to keeping overdue work visible. The
schema-13 fixture retains non-default household timing and a configured horizon.

The [schema-14 fixture](../../tests/fixtures/sqlite/v14.sql) was exported from
Domus source commit `449dc04c17a9c41d949d74cd341bf1e943a2fba9` after normal
household setup and task creation on Edge. Fixed maintenance materialized a
March 2026 Europe/Madrid occurrence whose original time falls in a clock gap.
The export also contains a manual task with the free-text tag `Garden`. It
preserves the task definitions, occurrence snapshots, fixed slot, original
command receipts, audit and outbox. The SQL export includes the source database's
application ID and schema version. Its SHA-256 is
`acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`.
