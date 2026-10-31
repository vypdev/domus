# Identity and storage implementation boundaries

Status: the M1 storage kernel, pure identity policy, transaction-bound local authorization and
session-lease core, HA adapters, standalone authentication API/CLI and application household/member/policy
commands are implemented on the Action-managed issue #6 branch. Persistent Edge.2 passes bounded
owner startup/session/reload/restart acceptance. Both standalone and native persistent household
APIs, console-approved recovery and manual snapshots are tested locally. Restore activation,
native product UI and complete deployment acceptance
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
They do not authenticate a submitted identity; only provider proof supplies it. The standalone
[household HTTP API](household-api.md) now adapts server-bound application services.
[The application commands](household-setup.md) explicitly initialize,
enroll, edit members and replace policy. External proof preparation holds no writer lock. Before
save, administrator transitions compare the prepared inventory, recheck current local authority and
preserve a proven eligible administrator. Shared application proof preparation imports only ports
and domain values. Setup-only mapping uses the unique durable setup audit actor; a missing or
ambiguous record cannot establish a new founder.

`domus.infrastructure.sqlite` implements those ports with separate connections and explicit SQL
transactions. Reads are query-only. Writers use `BEGIN IMMEDIATE` and a bounded wait, with no hidden
new-key retry. Schema/application/installation/channel checks precede mutations and repeat after
the writer lock. Initial schema creation uses transactional DDL, without `executescript`.
Unknown/future schemas and wrong ownership are refused. Receipts are retained and are never pruned
with activity; a future retention feature must preserve replay protection.

`domus.infrastructure.owned_storage` owns POSIX directory/file validation, lifecycle locking and
durable initialization/ready metadata. It generates a UUID only for an empty private directory and
passes an existing-only mode to SQLite after readiness, preventing silent empty replacement. The
native and standalone compositions initialize storage once before starting HTTP and release ownership
at shutdown, including listener failures. Standalone credential shutdown cannot prevent lease release.
Both explicit-file runtime factories reject an owned marker before SQLite initialization, even when
the owned runtime is stopped. Console attachment applies the same boundary.
All filesystem/locking primitives remain outside pure inner layers. See [data lifecycle](owned-data-directory.md).

Schema 2 added uniquely linked members and revisioned household policy. Its explicit additive
upgrade accepts the owned schema 1 checkpoint and preserves household data, receipts, audit and
outbox. Failure rolls back the entire DDL migration. The frozen old-schema fixture is independent
of current schema constants. See [migration limits](migrations-identity-storage.md).

Schema 3 adds recovery requests. The pure model binds target, installation/channel, policy/mapping
and member revisions to fixed ten-minute request and approval windows. Human commands require fresh provider proof;
the separate console use case obtains an explicit terminal decision outside the writer lock. The
transaction rechecks binding and commits approval or consumption/grant with receipt/audit/outbox.
Both HTTP compositions expose human routes while only domus-admin wires the console confirmation port.

Snapshot metadata remains pure and path-free. Application use cases consume a semantic archive port;
the SQLite adapter owns filesystem checks, read transactions, backup, hashes and integrity inspection.
Only the installation-console composition selects paths. [Manual snapshot evidence](evidence/m1-snapshots.json)
does not establish restore activation or newer-history reconciliation.

Restoration now adds pure complete-operation evidence and streaming reconciliation. Its semantic
application port binds preparation to an explicit checkpoint and installation. The SQLite adapter
seals the exact old database plus later facts in a new blocked directory, then independently verifies
hashes, projection and counts. It never replaces active data or starts a runtime. Historical replay,
runtime history storage, recovery rearm prevention and verified activation remain pending. See
[preparation boundaries](restoration.md) and the [complete SDD](../specs/platform-restoration.md).

One household per installation is reinforced by a singleton constraint. Household writes compare
the expected revision, and other input values use parameterized SQL. Outbox acknowledgements are
durable and duplicate-safe; delivering those events to HA is future work.

`SessionGuard` distinguishes bounded provider unavailability from explicit rejection. It requires
fresh proof for writes, while a read may use the latest known identity until the unchanged absolute
monotonic deadline. Rejection, expiry and identity mismatch deny access. A conditional in-memory
refresh cannot resurrect logout or overwrite a concurrently changed identity. Leases never contain
HA tokens or enter SQLite; their private session handles are omitted from diagnostic representations.
Restart requires authentication. This is tested with semantic
provider fixtures, not a claim of authentication on the owner's live HA.

The [HA adapters](ha-identity-protocol.md) now implement fixed operator endpoints, private OAuth
form exchange and correlated WebSocket proof, with explicit active/non-system provenance and
administrator/owner semantics. Supervisor's actual peer and a single candidate subject header precede
fresh Core lookup. The real pinned WebSocket client is exercised against disposable loopback servers,
including a negative cross-origin redirect fixture. No request may authenticate by constructing
an adapter value. The [native persistent runtime](native-household-api.md) now shares the household
routes, bounded local leases and fixed-origin CSRF. Edge.2 packages it and passes both native CPU-family
image checks plus bounded owner start/reload/restart acceptance.

`domus.application.authentication_values` and `session_values` own ephemeral login/lease contracts;
private browser/session material stays outside household domain entities. Application orchestration
atomically consumes browser-bound attempts before exchange and checks the returned target/deadline.
Concurrent callbacks cannot exchange twice.

`domus.infrastructure.standalone_sessions` privately binds HA credentials to leases, serializes fresh
proof/refresh per session and cannot restore a concurrently removed record. Unknown upstream
revocation is null, never fabricated success. Credentials remain bounded memory only.

`domus.entrypoints.http` owns strict DTOs, cookie/origin/CSRF checks, HTTP bounds, safe errors and actual
OpenAPI. `domus.entrypoints.household_http` owns strict business DTOs and uses a common HTTP contract
module, separate from domain records. `domus.composition.server` wires the standalone CLI with one
worker, disabled proxy rewriting and no access/query logging. Its optional --database enables
composition.household, private session actors/directory and local query services. Sign-in creates
no household. See [configuration](configuration.md),
[the user journey](identity-household.md) and [operations](operations-identity-storage.md).

`domus.composition.ingress` wires both native runtime forms. Installed Edge.2 uses
`domus.composition.ha_app` to provision its private child and exec the persistent runtime without
root privileges. [Original preview acceptance](evidence/m1-native-ha-acceptance.json) is distinct from
[persistent owner acceptance](evidence/m1-persistent-ha-acceptance.json). Neither establishes complete
product, live household-command or standalone-browser acceptance.

Its optional persistent composition uses the same household router and services as standalone.
Infrastructure binds local leases to keyed digests of the existing Supervisor session and installation
context; no raw cookie is persisted. The native entrypoint verifies configured origins and CSRF,
while the application still requires fresh human proof and current transaction-time Domus authority.
Technical Core directory access never sets the actor's role. See the
[native runtime evidence](evidence/m1-native-household-api.json) for exact tests and remaining packaging.

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
These fixtures alone do not establish live HA or complete packaged acceptance. The separate
[member](evidence/m1-member-administration.json) and [policy](evidence/m1-policy-administration.json)
checkpoints add real-file authority races, canonical retries and provenance checks. The
[HTTP checkpoint](evidence/m1-household-api.json) adds production standalone composition, strict JSON,
read-grace/authority boundaries and schema tests. Native persistent packaging, restore and full M1
acceptance remain outstanding.

See [development checks](development.md), [owner decisions](decisions.md),
[the companion](../specs/platform-foundation-identity-sqlite.md), and
[initial storage evidence](evidence/m1-storage-kernel.json) and
[identity-policy checkpoint evidence](evidence/m1-identity-policy.json).
The subsequent [protocol evidence](evidence/m1-ha-protocol.json) identifies the adapter sources,
reviewed Core blobs, fictitious provider fixtures and outstanding live/package acceptance.
