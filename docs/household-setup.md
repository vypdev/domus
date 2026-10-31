# Household setup command checkpoint

Status: application use cases and real SQLite tests implemented. HTTP/UI wiring and member/policy
administration are pending. The installed Edge 0.0.0-edge.1 connection preview contains none of these
commands and creates no household data.

## Explicit setup

The first browser arrival grants no authority. Setup is an explicit command from a currently proven
active human HA administrator. It creates one household, its timezone, administrator mapping and
linked active member records in one transaction. A server-owned household ID prevents client scope
selection. Name whitespace is normalized, the IANA timezone must exist and initial revision must be
the integer zero. There is no silent timezone fallback.

| Mapping | Initial administrator source |
|---|---|
| All HA administrators, default | Current HA administrator proof and an active linked membership |
| Setup administrator only | The setup actor while that account remains a current HA administrator |
| Selected user | The exact eligible selected HA human, who may be an ordinary HA user |

Selected setup verifies the target before opening the writer transaction. It creates the target's
active linkage if different from the actor. Base profiles are viewers; inherited administration
comes from the mapping and current facts. It is not accidentally persisted as an independent grant.
Changing the mapping later must preserve any deliberately granted independent administrator profile.

## Joining and editing

An eligible human explicitly enrolls their own HA identity. The command cannot submit a different
actor, profile or active status. New ordinary members are pending viewers. A current HA administrator
becomes active on enrollment only under the all-administrators mapping. Existing suspended or
archived membership blocks enrollment and replay; account linkage and history are retained.
Activation and profile assignment by an authorized administrator still require their own command
implementation. Capacity is 256 total member records, including archived history; saturation rejects
new enrollment without removing an actor or appending partial evidence.

An active member with current household-management permission may edit the home name and timezone.
Updates use the expected current revision. A stale revision is a conflict, with no automatic retry
under a new command key. An HA outage blocks setup, enrollment and edits before mutation.

## Durable results and source boundaries

State, scoped idempotency receipt, audit and outbox commit together. The same key and canonical
payload return the original receipt after current authorization, including after restart. A changed
payload conflicts. A revoked or suspended actor cannot use an old receipt to regain access. An
authorized replay does not depend on recontacting an unrelated selected target or timezone provider.
Every new effect rechecks local authority and replay inside the serialized writer transaction.
No external directory or timezone preparation holds that writer lock.

The HA directory adapter performs at most one bounded lookup for a batch of up to 256 exact user IDs.
Confirmed missing, inactive or system users are omitted. Malformed or duplicate directory records,
transport failure and authorization denial raise instead of returning a misleading partial result.
Technical transport privilege supplies facts and never becomes the human's household grant.

These are application boundaries, not a new public API. Member activation/editing, policy changes,
last-administrator command safeguards, console recovery, snapshot/restore, native local sessions and
production installation persistence remain outstanding. See
[the governing companion](../specs/platform-foundation-identity-sqlite.md),
[identity behavior](identity-household.md) and [evidence](evidence/m1-household-commands.json).
