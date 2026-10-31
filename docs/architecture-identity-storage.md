# Identity and storage implementation boundaries

Status: M1 storage kernel implemented on the Action-managed issue #6 branch. HA identity,
membership policy, recovery, snapshots, HTTP/console entrypoints and live deployment acceptance
remain pending. The [owning companion](../specs/platform-foundation-identity-sqlite.md) retains
the complete increment contract; this checkpoint does not complete M1 or the product.

## Implemented dependency direction

`domus.domain.storage` defines immutable installation identity, household records, scoped command
keys and canonical JSON documents. It imports no framework, database, network or global clock.
Decoded documents are detached copies, and invalid/ambiguous JSON cannot acquire a replay digest.

`domus.application.ports` defines semantic household, receipt, audit, outbox and transaction ports.
`AtomicCommands` requires an injected authorization policy; it has no permissive production default.
It checks that policy inside the write transaction before examining a previous receipt. Identical
authorized replay returns the original result; changed payload conflicts. A new effect, receipt,
audit fact and outbox event commit together. Concrete membership/HA authorization is still pending;
test doubles prove the orchestration contract without pretending to authenticate a user.

`domus.infrastructure.sqlite` implements those ports with separate connections and explicit SQL
transactions. Reads are query-only. Writers use `BEGIN IMMEDIATE` and a bounded wait, with no hidden
new-key retry. Schema/application/installation/channel checks precede mutations and repeat after
the writer lock. Initial schema creation uses transactional DDL, without `executescript`.
Unknown/future schemas and wrong ownership are refused. Receipts are retained and are never pruned
with activity; a future retention feature must preserve replay protection.

One household per installation is reinforced by a singleton constraint. Household writes compare
the expected revision, and other input values use parameterized SQL. Outbox acknowledgements are
durable and duplicate-safe; delivering those events to HA is future work.

The composition and entrypoint packages reserve the accepted architecture boundaries. They do not
contain an HTTP server, CLI or product UI yet and are not registered as implemented entrypoints.

## Verification scope

The separate backend CI job measures every authored `domus` module at 100% supported line/statement
and branch coverage. Tooling coverage remains independent. The architecture job checks the actual
backend graph as well as the existing forbidden-import/cycle fixtures. The aggregate requires every
suite on every PR update, including documentation changes.

Real-file tests cover rollback at every durable stage, process death before commit, reopened state,
two-process writer contention/stale revisions, overlapping identical commands, current-policy replay
denial, schema/ownership refusal without changing existing file bytes, and initial migration rollback.
These fixtures do not establish HA authentication, full application behavior or packaged acceptance.

See [development checks](development.md), [owner decisions](decisions.md),
[the companion](../specs/platform-foundation-identity-sqlite.md), and
[checkpoint evidence](evidence/m1-storage-kernel.json).
