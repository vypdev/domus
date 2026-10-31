# Household API checkpoint

Status: strict HTTP routes, local queries and standalone SQLite composition are implemented.
Native persistent wiring, the product UI, recovery and snapshots are still pending. The installed
Edge 0.0.0-edge.1 app remains the earlier stateless connection preview; it contains none of these routes.

## Run with persistent standalone data

Add `--database /owned/data/domus.sqlite3` to the [standalone command](configuration.md). The parent
directory must exist and be owned by the installation operator. Keep the same explicit installation
UUID and channel when restarting. SQLite initialization validates ownership/schema/channel before
opening or migrating the database; another channel cannot adopt it. Stable and Edge require separate
files and installation identities. No HA credential or session token enters these business tables.

Without this option the executable retains its authentication-preview behavior and opens no business
database. This is a development checkpoint, not the final deployment package. HA app installation
continues to use existing Ingress authentication without requiring standalone OAuth as a prerequisite.

Signing in, opening the authorization endpoint or starting with a new database does not initialize a
household or enroll anyone. Setup and enrollment are explicit commands. See
[the application rules](household-setup.md) and [the actual OpenAPI contract](contracts/household-api.openapi.json).
The live `/api/v1/openapi.json` includes the installation's own cookie namespace; the checked reference
uses the fixture namespace and contains schemas only, with no live credentials or account records.

## Routes and authority

All routes use the validated server-owned session. Forwarding/Ingress identity headers are rejected
by the standalone listener. These routes do not accept an actor, installation ID or household selector.

| Route | Meaning | Current local authority |
|---|---|---|
| GET /api/v1/authorization | Own setup/enrollment/member state and M1 permission view | Verified human or an original unexpired read-grace session |
| GET /api/v1/household | Household name, timezone and revision | Household read |
| GET /api/v1/members | Bounded roster, at most 256 records | Member read; other people's HA linkage/exceptions need member-management permission |
| GET /api/v1/policy | Current mapping, adjustments and revision | Policy management; this is a read and may use valid outage grace |
| GET /api/v1/operations/{operation_id} | Own original committed result and observed event-delivery state | Own operation read plus the original command permission |
| POST /api/v1/household | Explicit setup, expected revision zero | Fresh HA administrator before setup; current household administrator for privileged replay |
| PUT /api/v1/household | Name/timezone edit | Fresh human and current household management |
| POST /api/v1/members/enrollment | Explicit own enrollment, expected revision zero | Fresh eligible human and current enrollment rules |
| PUT /api/v1/members/{member_id} | Profile/status/ordinary exception replacement | Fresh human and current member management; last-administrator safeguard |
| PUT /api/v1/policy | Mapping/profile-adjustment replacement | Fresh human and current policy management; provenance and last-administrator safeguards |

The authorization permission list is explicitly scoped to `household_administration`. It is not a
global authorization answer for tasks, inventory or another member's preferences. Later domain APIs
must derive assignment/ownership facts on the server. A member's roster profile is the explicit base
profile, not a claim of another person's currently inherited HA administrator source. The own access
view separately reports effective_role from that person's verified source and the current mapping.

Pending/unlinked people can see their own access state without gaining household reads. Suspended
or archived members cannot self-reactivate. Active members may see their own linkage/exceptions;
ordinary roster reads omit those fields for everyone else. Policy and operation queries reread local
authority in the same read transaction; an old service instance is not a permission cache.

## Write and retry contract

Every write requires one `Origin` matching the configured public origin, one session-bound
`X-CSRF-Token`, and one `Idempotency-Key`. Obtain CSRF from `/api/v1/auth/csrf`. Keys are 1–128
characters, start with an ASCII letter/digit and otherwise use letters/digits, underscore, dot,
colon or hyphen. Missing, duplicate and malformed keys are rejected. Every body includes the expected
revision. Invalid types, unknown fields and protected permission overrides are rejected.

Bodies must be UTF-8 JSON objects with `application/json` (optionally `charset=utf-8`). Duplicate JSON
keys, nonfinite values, malformed encoding and excessive nesting cannot be silently normalized into a
different command. Query parameters are empty for this checkpoint, including writes. Shared transport
bounds remain 65,536 body bytes, 100 headers/16,384 bytes and a five-second body-receiving deadline.

Current authorization precedes receipt disclosure. The same key and canonical payload return the
original result even after restart, before stale-revision handling. A changed payload returns 409;
a stale new write or inventory changed during proof also returns 409. There is no automatic rebase
or retry under a new key. A busy writer returns `storage_busy`/503 with `Retry-After: 1`; retry only
the identical request/key. Rejected transitions never append partial state, receipt, audit or outbox
evidence. An unexpected 500 cannot prove that a change was not committed: its message preserves that
uncertainty and instructs the client to retry the original payload/key or inspect the operation.
An injected failure after commit verifies that this retry returns one original effect and receipt.

A successful write returns `state=committed`, operation ID, original result and UTC creation time.
It does not claim that outbox delivery has completed. The operation query observes pending/delivered
from the exact event record, without guessing from a limited queue page. Missing/corrupt atomic
records fail safely. Another actor's operation returns a scoped 404 after current authorization;
unlinked or suspended actors cannot probe its existence. Privilege loss also blocks disclosure of
old privileged results. HTTP has no recovery-approval endpoint.

## HA availability and remaining deployment work

Reads may use the original unexpired lease during a bounded HA availability failure; current local
policy still applies. Writes always reprove the exact human. Rejection, identity mismatch, expiry
or logout cannot become read grace or revive an old credential. Directory lookup serializes use of
private delegated material, checks the session before and after I/O and preserves the absolute lease
deadline. Source/directory permission failure never promotes a transport account or permits a guessed identity.

The standalone directory currently uses the requesting person's delegated HA grant. HA may deny
directory access to an ordinary HA account even when that person has a deliberate Domus administrator
profile. Changes requiring other people's source proof then fail closed. Complete first-release
standalone authority needs the planned companion/installation wiring; this checkpoint does not claim
that capability complete. Native Ingress will use its existing private Core transport authority while
preserving the separate exact-human command actor. The existing gateway is unchanged.

See [checkpoint evidence](evidence/m1-household-api.json), [identity](identity-household.md),
[operations](operations-identity-storage.md) and [native installation](installation-home-assistant.md).
