# Identity and storage migrations

The M1 checkpoint below introduced schema 4. The development task source now uses schema 7;
see [task migration](tasks/migration.md) for versions 5–7, frozen inputs and rollback. Installed
Edge.3 remains pinned to the separate M1 source. Source tests do not establish a released upgrade.

| Version | Introduced state | Upgrade behavior |
|---|---|---|
| 1 | Installation/channel marker, one household, durable command receipts, audit, outbox | Frozen development checkpoint at 95458b84b6521b203fab3a257137f24978a03e82 |
| 2 | Member linkage, explicit profile/exceptions, household administrator mapping/profile adjustments | Add tables atomically; retain every version 1 record |
| 3 | Target-bound administrator recovery requests and optimistic approval/consumption state | Add recovery table/index atomically; preserve version 1/2 identity and replay records |
| 4 | Retained complete operation evidence, current/historical placement, first archive provenance and indexed recovery closure | Add history table/index atomically; preserve all earlier business and replay records |

Initialization inspects schema, application marker, installation UUID and channel before mutation,
then repeats inspection after obtaining the bounded writer lock. Only an empty owned destination or
the explicitly supported prior versions can be initialized/upgraded. Normal transactions require the
current version. An unknown future version, unrelated database or mismatched ownership is refused;
Domus never generates a different identity to adopt an existing file.

The additive migration uses individual DDL statements inside `BEGIN IMMEDIATE`, with the version
advance in that same transaction. Failure or cancellation rolls back all new tables and the version.
Read-only frozen SQL fixtures from the version 1, version 2 and version 3 checkpoints exercise preservation of
household revision, receipt result, audit detail and pending outbox identity. Mid-migration failure leaves
the original file unchanged and a subsequent deliberate initialization succeeds.

No policy or administrator is invented for a version 1 household that has none. Protected access
fails closed until a separately verified setup/recovery path is implemented; it must not be resolved
by granting administration to the next browser. Schema 3 adds recovery for an already configured
policy through [current HA authority and the installation console](administrator-recovery.md).
It does not invent policy for an old unconfigured household. Do not use direct SQL to bypass setup.

Member IDs and HA linkage remain stable even after archival. A second link to the same HA user is
rejected; ordinary updates cannot relink history. Member and policy writes compare expected revisions.
Administrator grants derived from a mapping remain distinct from independent explicit member roles.
An already committed command receipt is retained across upgrade; returning it still requires current
authorization. Recovery approval consumption and the explicit grant commit with their new receipt,
audit and outbox. Credentials and session leases are absent from every business schema version.

Schema 4 permits historical facts to outlive a current household without recreating business rows.
Its separate infrastructure-only import preserves current acknowledgements and the global outbox
sequence, validates complete retained history and rolls back its savepoint on failure. New snapshots
include that history. [Runtime lookup and recovery guards](restoration.md) are tested through both
APIs and actual offline activations. The local Edge.3 image also upgrades actual Edge.2 data and
restores its schema-3 snapshot; complete deployment acceptance remains pending. The frozen schema-3 fixture was captured from
002a982ee60b8aa22a707de402ab1e8fc0306be5 before changing the schema, independently of new constants.

Rollback needs a compatible application/database pair. Never run an older application on a newer schema
or decrement `user_version` manually. [Snapshot creation/inspection](snapshots.md) is implemented;
offline restoration to a verified same-installation/channel generation is implemented locally.
Cross-architecture/live restore, destructive-upgrade backups, package hooks and operational
recovery/retention acceptance remain pending in the [M1 companion](../specs/platform-foundation-identity-sqlite.md).
