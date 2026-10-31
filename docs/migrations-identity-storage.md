# Identity and storage migrations

Status: schema 1 to schema 2 is an implemented additive upgrade within the M1 development branch.
This does not establish a released package upgrade, restore command or HA authentication journey.

| Version | Introduced state | Upgrade behavior |
|---|---|---|
| 1 | Installation/channel marker, one household, durable command receipts, audit, outbox | Frozen development checkpoint at 95458b84b6521b203fab3a257137f24978a03e82 |
| 2 | Member linkage, explicit profile/exceptions, household administrator mapping/profile adjustments | Add tables atomically; retain every version 1 record |

Initialization inspects schema, application marker, installation UUID and channel before mutation,
then repeats inspection after obtaining the bounded writer lock. Only an empty owned destination or
the explicitly supported prior version can be initialized/upgraded. Normal transactions require the
current version. An unknown future version, unrelated database or mismatched ownership is refused;
Domus never generates a different identity to adopt an existing file.

The additive migration uses individual DDL statements inside `BEGIN IMMEDIATE`, with the version
advance in that same transaction. Failure or cancellation rolls back all new tables and the version.
A read-only frozen SQL fixture from the old checkpoint exercises preservation of household revision,
receipt result, audit detail and pending outbox identity. The injected mid-migration failure leaves
the original file unchanged and a subsequent deliberate initialization succeeds.

No policy or administrator is invented for a version 1 household that has none. Protected access
fails closed until a separately verified setup/recovery path is implemented; it must not be resolved
by granting administration to the next browser. Schema 2 is currently a development checkpoint,
without a runnable setup/console entrypoint. Do not use direct SQL to bypass identity setup.

Member IDs and HA linkage remain stable even after archival. A second link to the same HA user is
rejected; ordinary updates cannot relink history. Member and policy writes compare expected revisions.
Administrator grants derived from a mapping remain distinct from independent explicit member roles.
An already committed command receipt is retained across upgrade; returning it still requires current
authorization. Credentials and session leases are absent from both schema versions.

Rollback needs a compatible application/database pair. Never run an older application on schema 2
or decrement `user_version` manually. Snapshot/restore primitives, verified activation to a new
same-installation/channel directory, destructive-upgrade backups, package hooks and operational
recovery/retention acceptance remain pending in the [M1 companion](../specs/platform-foundation-identity-sqlite.md).
