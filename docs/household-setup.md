# Household setup command checkpoint

Status: application household/member/policy use cases, standalone HTTP wiring and real SQLite tests
are implemented in both native and standalone compositions and packaged in Edge.3. The current
[owner acceptance](evidence/m1-edge3-ha-acceptance.json) covers its connection page/restart only;
product UI and live household setup remain pending. Startup never implicitly creates a household.

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
Activation and profile assignment are explicit administrator commands. Capacity is 256 total member
records, including archived history; saturation rejects
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

## Administrator member changes

The member-update command replaces the target's profile, status and ordinary permission exceptions
at an expected revision. It cannot replace the member ID, HA linkage or household. Activating or
editing an active target requires fresh exact eligible-human proof; deactivating an unavailable target
is possible when the freshly proven actor still guarantees a remaining administrator. Administrator
permission is checked again inside the writer transaction. After any external lookup the actor is
reproved, so a known source rejection or identity change blocks the command.

Before saving, the command checks that the full policy/member snapshot used to prepare proof is still
current and that a currently eligible administrator remains in the proposed state. Relevant alternative
administrators are verified in one bounded batch when required; missing/ineligible users cannot satisfy
the safeguard. A source outage blocks instead of becoming a claim of absence. Two concurrent removals
cannot both commit from the same old administrator inventory. No proof or directory lookup holds the
SQLite writer lock. HA proof and SQL still cannot form a globally atomic snapshot across systems.

Suspension applies immediately to existing local authorization and old-receipt access. An authorized
administrator can deliberately reactivate an archived member after fresh HA proof, preserving the same
linkage and history. Identical concurrent updates share one effect and receipt. Rule order is normalized
for idempotency. Member transitions, audit, receipt and outbox share one commit; a stale inventory or
revision returns a conflict without automatic rebase. See
[the member checkpoint evidence](evidence/m1-member-administration.json).

## Household policy changes

Current household administrators may explicitly replace the mapping and household profile adjustments
at an expected policy revision. Adjustments cannot grant administrator-only permissions or weaken
domain constraints. An active selected ordinary HA human can administer the household, including
changing policy, through that deliberate Domus grant. Technical directory privilege supplies human
facts; it never replaces the command actor's own permission.

Selected/setup targets must already have an active linked membership and fresh eligible-human proof.
The setup-only mode is tied to the unique committed setup actor in durable audit; the request cannot
designate a different founder. The designated founder must still be a current HA administrator.
Missing or ambiguous setup provenance blocks this mapping instead of inventing a new installer.
The bounded audit lookup returns at most two candidates; no complete audit is materialized.

A mapping change recalculates inherited authority and preserves independent administrator profiles.
The proposed policy must retain a freshly eligible administrator. An alternate administrator lookup
is bounded; unavailable or rejected proof cannot turn into a guessed grant. After external proof the
actor is reproved. Inside the writer transaction the actor must still have current policy-management
permission, the member/policy inventory must still match, and the proposed state must retain an
administrator. No member row is rewritten merely to change household policy.

Policy, receipt, audit and outbox commit together. Reordered equivalent adjustments share a canonical
payload. Authorized replay survives restart and occurs before stale-revision checks, but a mapping
change that removes the actor's permission also removes their ability to disclose an old privileged
receipt. See [policy evidence](evidence/m1-policy-administration.json).

The HA directory adapter performs at most one bounded lookup for a batch of up to 256 exact user IDs.
Confirmed missing, inactive or system users are omitted. Malformed or duplicate directory records,
transport failure and authorization denial raise instead of returning a misleading partial result.
Technical transport privilege supplies facts and never becomes the human's household grant.

The [standalone household API](household-api.md) now exposes these commands and current local queries.
Native persistent wiring, console recovery, snapshot/restore, native local sessions and
production installation persistence remain outstanding. See
[the governing companion](../specs/platform-foundation-identity-sqlite.md),
[identity behavior](identity-household.md) and [evidence](evidence/m1-household-commands.json).
