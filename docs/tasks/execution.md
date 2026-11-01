# Task execution API

The development backend exposes the same task application services in the native HA app and
standalone Container composition. The product task interface, material settlement and real domain
consumers remain incomplete. This API is not first-release acceptance or evidence of owner adoption.

Native access uses the existing trusted HA Ingress session. Standalone access uses its existing
Domus session after HA authorization. There is no additional task login. Every change requires fresh
HA proof, current local permissions, Origin, the session's `X-CSRF-Token` from `/api/v1/auth/csrf`
and an `Idempotency-Key`. Never copy transport credentials into a task body.

All routes below are under `/api/v1/tasks`. Both actual composed schemas are retained:
[standalone](../contracts/household-api.openapi.json) and
[native](../contracts/native-household-api.openapi.json).

## Create and read

POST `/definitions` accepts a title-only body:

```json
{"title": "Wipe table"}
```

Creation defaults to revision zero and active/available work. One transaction creates the definition,
first occurrence, any absent task defaults, original receipt, audit and source event. Optional content
fields are `description`, `priority`, `tags` and initial `state` (`draft` or `active`). Optional policy
values belong to `overrides`; supplying a real override also needs administrator configuration
authority. Household, account, member attribution for claims, installation and channel are server-bound.

GET `/definitions` and `/occurrences` return `items` and `next_cursor`, with 25 items by default and
at most 100. Use a canonical integer `limit` and return the cursor with the same filters and limit.
Definition lists accept `state`; occurrence lists additionally accept `assignee_id` and
`definition_id`. Unknown or duplicate query parameters fail. Cursors expire after five minutes by
default and can become invalid after a process restart. Pages are not a cross-page snapshot.

GET `/definitions/{id}` returns current definition facts. GET `/occurrences/{id}` returns its frozen
definition snapshot, current policy rules, required work, current cycle and action hints. Hints do
not authorize a later change; the command checks again. GET `/policy` returns defaults with revision
zero when absent and never initializes them.

Definition reads include frozen material binding/planned-quantity facts. A quantity is a canonical
decimal string such as `"0.25"`, never a floating-point number or an internal `{value: ...}` object.
Create/update now accept `materials`, a list of at most 32 unique selections such as
`{"reference_id": "inventory-reference", "planned_quantity": "0.25"}`. Only Inventory resolves
product, unit, location and current precision; clients cannot substitute those fields. Explicit
link/replacement/clear requires current task authority and inventory.manage, including receipt
replay. Omitted/null preserves the original canonical request; explicit `[]` remains distinct.
The default composition has no real Inventory provider yet: nonempty linking returns a safe 503
before any task/default/receipt is written. Fixtures do not supply a product catalog or stock ledger.

## Edit and assign

PUT `/policy` requires an expected revision and nested `rules`. Revision zero initializes absent
defaults. It is administrator-only. Rule defaults include eligible self-claim, role-default
verification, participant-adult approval, task-scoped materials and the performed prerequisite gate.
Material settings are policy facts; only an actual Inventory provider can confirm stock consumption.

PUT `/definitions/{id}` replaces content/lifecycle fields at the expected positive revision.
Omitted or null `overrides` preserves existing values; an empty object resets inheritance and also
requires configuration authority. Existing occurrences and cycles keep their original snapshots.
Paused/archived definitions do not create new work.

POST `/definitions/{id}/occurrences` creates work with optional `assignee_ids`, `prerequisite_ids`,
`required_subtask_ids` and UTC millisecond `due_at`. Each ID list is unique and bounded to 32.
PUT `/occurrences/{id}/assignment` replaces assignees; an empty list explicitly releases eligible
work. PUT `/occurrences/{id}/dependencies` replaces both required-work lists. Current management,
resource scope, revision, graph acyclicity and eligible lifecycle state are checked transactionally.

## Claim, perform and verify

POST `/occurrences/{id}/claim` accepts only the expected revision. It derives the sole claimant from
the verified actor. Eligible restricted members may claim available work by default; household/task
configuration may disable it. A claim does not waive adult verification.

POST `/occurrences/{id}/transition` accepts `expected_revision`, `target` and optional `reason`.
Block, cancel and skip decisions require a meaningful reason. Completion and reopening have dedicated
commands; a state setter cannot bypass them.

POST `/occurrences/{id}/complete` accepts:

```json
{
  "expected_revision": 2,
  "performer_ids": ["member-id"],
  "performed_at": 1793491200000
}
```

The example timestamp is a UTC millisecond instant, not a value to reuse for new work. Actual
performers, recording actor and assignees are distinct. Recording for others needs a separate grant.
A restricted actor must be assigned and include themselves. Completion snapshots performer profiles,
effective policy/revisions and actual work time. Future work time is invalid. Dependencies must be
performed by default; the configurable approved gate additionally waits for required verification.

Adult-only performance needs no verification by default. Any restricted performer requires a current
authorized adult. POST `/occurrences/{id}/verify` accepts revision, `cycle_id`, `decision`
(`approved`/`rejected`) and a nonblank reason for rejection. Participant-adult approval is allowed by
default; an independent-adult policy remains available. Approval does not close the cycle.

POST `/occurrences/{id}/reopen` requires revision, original current `cycle_id` and a meaningful reason.
It closes that cycle, preserves performed/verification facts and opens the occurrence without
automatically reopening completed dependents. Its source event is not proof of points compensation,
stock return or a completed review projection.

Completion additionally accepts up to 32 unique `material_usages`, for example
`[{"line_id": "server-created-line", "quantity": "0.5"}]`. Use only frozen line IDs from the
occurrence. Identity, canonical quantity and unit precision are validated before work effects.
Missing actuals remain unknown; explicit zero requests no movement. Valid work survives ordinary
material denial, shortage or provider absence with a visible pending outcome. Separate recording
also waits for deliberate settlement. Approval, reopening, stock/grant changes and receipt replay
never retry consumption automatically.

GET `/occurrences/{id}` includes current-cycle `materials`. GET `/occurrences/{id}/materials`
requires the original `cycle_id` and returns current outcomes for that scoped open or closed cycle,
in frozen line order with at most 32 entries. Both reads recheck current task-read permission, use
one local read transaction and never contact Inventory. A cycle absent after restoration returns
404; its retained original operation remains historical evidence rather than current state.

Each outcome distinguishes submitted quantity, desired `quantity`, state/pending reason and the
last `confirmed_quantity`, `confirmed_effect_revision`, `posted_at` and movement reference. A pending
correction cannot claim its desired total has already been consumed. Reopening removes the current
cycle projection but leaves its explicit original-cycle query available. Original receipt outcomes
stay unchanged. Explicit post/correct/dismiss commands still require implementation. Decision A36
allows any currently authorized material participant to correct confirmed consumption while
preserving original facts and requiring Inventory confirmation.

## Recover a result and inspect history

Keep the original payload, key and operation ID. A stale revision/different key cannot replace an
uncertain result. If the response fails after commit, retry the same request/key. GET
`/operations/{id}` looks up only your own task operation and rechecks the original command's current
authority, including configuration and on-behalf grants. The common household operation endpoint
continues to own household administration; task receipts use this task-specific route.

GET `/occurrences/{id}/history` returns safe chronological pages. It exposes local member attribution
and selected task facts, without raw HA account identifiers or canonical internal requests. Restored
operations whose effects are absent are marked historical; current retained projections appear once.
An original historical receipt never authorizes replaying its effect. Review current state before
deliberately requesting fresh work with a new key.

Receipt results remain immutable. `delivery` concerns only generic outbox acknowledgement; it does
not confirm Inventory, Points or recurrence acceptance. A historical effect reports suppressed
delivery. Current task cycle/source results explicitly retain `consumer_delivery: "unconfirmed"`.

Existing valid sessions may read local tasks during temporary HA unavailability, subject to current
local permissions and the original session expiry. Changes remain blocked until HA can reverify the
actor. Explicit HA rejection removes access instead of opening an outage grace period.
