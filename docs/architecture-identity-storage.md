# Identity and storage implementation boundaries

Status: the M1 storage kernel, pure identity policy, transaction-bound local authorization and
session-lease core are implemented on the Action-managed issue #6 branch. HA protocol adapters,
membership use cases, recovery, snapshots, HTTP/console entrypoints and live deployment acceptance
remain pending. The [owning companion](../specs/platform-foundation-identity-sqlite.md) retains
the complete increment contract; this checkpoint does not complete M1 or the product.

## Implemented dependency direction

`domus.domain.storage` defines immutable installation identity, household records, scoped command
keys and canonical JSON documents. It imports no framework, database, network or global clock.
Decoded documents are detached copies, and invalid/ambiguous JSON cannot acquire a replay digest.

`domus.domain.identity` defines eligible human facts, all three administrator mappings, immutable
member/profile rules and deterministic permission precedence. A selected active human need not be
an HA administrator. A mapping grant is derived from current proof, separately from the member's
explicit role, so a source change removes inherited authority without deleting an independent grant.
Inactive local state, scope, private self-only access and required adult approval take precedence.
Ordinary overrides cannot configure protected administrator controls. The administrator-retention
policy evaluates supplied current identity facts; it cannot make an HA directory and SQLite atomic.

`domus.application.ports` defines semantic household, member/policy, receipt, audit, outbox and
transaction ports.
`AtomicCommands` requires an injected authorization policy; it has no permissive production default.
It checks that policy inside the write transaction before examining a previous receipt. Identical
authorized replay returns the original result; changed payload conflicts. A new effect, receipt,
audit fact and outbox event commit together. `HouseholdAccess` and `MembershipAuthorization` now
resolve current membership/policy inside that transaction and bind the action to the proven actor.
They do not authenticate a submitted identity; the HA adapter and use-case entrypoints are pending.

`domus.infrastructure.sqlite` implements those ports with separate connections and explicit SQL
transactions. Reads are query-only. Writers use `BEGIN IMMEDIATE` and a bounded wait, with no hidden
new-key retry. Schema/application/installation/channel checks precede mutations and repeat after
the writer lock. Initial schema creation uses transactional DDL, without `executescript`.
Unknown/future schemas and wrong ownership are refused. Receipts are retained and are never pruned
with activity; a future retention feature must preserve replay protection.

Schema 2 adds uniquely linked members and revisioned household policy. Its explicit additive
upgrade accepts the owned schema 1 checkpoint and preserves household data, receipts, audit and
outbox. Failure rolls back the entire DDL migration. The frozen old-schema fixture is independent
of current schema constants. See [migration limits](migrations-identity-storage.md).

One household per installation is reinforced by a singleton constraint. Household writes compare
the expected revision, and other input values use parameterized SQL. Outbox acknowledgements are
durable and duplicate-safe; delivering those events to HA is future work.

`SessionGuard` distinguishes bounded provider unavailability from explicit rejection. It requires
fresh proof for writes, while a read may use the latest known identity until the unchanged absolute
monotonic deadline. Rejection, expiry and identity mismatch deny access. A conditional in-memory
refresh cannot resurrect logout or overwrite a concurrently changed identity. Leases never contain
HA tokens or enter SQLite; their private session handles are omitted from diagnostic representations.
Restart requires authentication. This is tested with semantic
provider fixtures, not a claim that the live HA protocol is implemented.

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
Additional tests cover policy precedence/source revocation, concrete authorization before replay,
schema 1 upgrades, duplicate HA linkage, scoped optimistic writes, and session outage/expiry/races.
These fixtures do not establish HA authentication, complete membership commands or packaged acceptance.

See [development checks](development.md), [owner decisions](decisions.md),
[the companion](../specs/platform-foundation-identity-sqlite.md), and
[initial storage evidence](evidence/m1-storage-kernel.json) and
[identity-policy checkpoint evidence](evidence/m1-identity-policy.json).
