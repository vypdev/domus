# Proposed Home Assistant entity and service contract

Status: Draft. Public identifiers below are proposals to review before implementation.
The existing Home Assistant gateway is already integrated. No gateway installation, code change,
MCP transport or MCP tool implementation belongs to this contract.

## Source of truth and identity

Domus owns its task, shopping, stock and points records. HA entities are derived views.
Existing unrelated native task/shopping lists remain untouched; future import would need its own reviewed policy.
Each installation/channel has a stable instance ID. Entity unique IDs include that ID and record identity,
so renaming an entity or co-installing Edge cannot alias Stable.
Services are registered once in HA under domus; selectors require a configured integration entry/instance,
and multi-instance calls must explicitly choose it. Names are stable English identifiers in every UI locale.

## Entities

| Proposed entity | State / semantics | Attributes or retrieval |
|---|---|---|
| sensor.domus_tasks_due | Count of pending due occurrences in household local day | freshness and bounded summary; detailed items via query_tasks |
| sensor.domus_tasks_overdue | Count of past-due incomplete occurrences | same count/filter semantics as UI |
| sensor.domus_low_stock_products | Count of active policies below threshold | query_inventory for details |
| sensor.domus_member_points_<member> | Current household-week total for one member | stable member reference; ledger query for history |
| binary_sensor.domus_attention_required | Any authorized actionable household condition | bounded reason codes, never an unbounded record list |
| calendar.domus_schedule | Planned occurrence windows and due-date markers | stable UID; actual completion is not substituted |
| calendar.domus_completion_history | Optional separate actual-work timeline | completion UID and actual timestamp; explicit history label |
| todo.domus_tasks | Supported task occurrence projection with stable item UID | read plus only explicitly implemented native features |
| todo.domus_shopping | Outstanding purchasing intent | initially read-only; checkbox cannot silently mean receipt/stock posting |

Actual entity_ids are assigned by HA and may have channel/instance suffixes; clients discover them.
Availability is unavailable when authoritative data cannot be read; empty successful collections remain empty success.
State properties read cached projection data and do not perform blocking network calls.

## Services

All services validate household/instance scope. Mutations accept an idempotency key and relevant expected revision.
Common responses are bounded and versioned. Query services return a response; native services only advertise features
whose semantics are supported. No arbitrary SQL, Python, URL proxy, shell or raw backend passthrough is exposed.

| Proposed service | Purpose / important fields | Result |
|---|---|---|
| domus.query_tasks | filters, range, page_size, cursor | authorized occurrence summaries |
| domus.get_task | occurrence_id | definition snapshot, state, requirements and revision |
| domus.create_task | title and optional advanced policy | definition_id and occurrence_id |
| domus.update_task | definition_id or occurrence_id, expected_revision, explicit change | revised record; no historic rewrite |
| domus.assign_task | occurrence_id, assignee_ids | assignment revision and actual unchanged facts |
| domus.start_task | occurrence_id | state transition |
| domus.complete_task | occurrence_id, performer_ids | completion_id and verification/award status |
| domus.verify_task | completion_id, decision, reason | authorized verification result |
| domus.reopen_task | occurrence_id, reason | reopening and linked compensation status |
| domus.skip_task | occurrence_id, reason | retained recurring exception |
| domus.reschedule_task | occurrence_id, explicit local date/instant | new planned window preserving original history |
| domus.pause_task_schedule | definition_id, paused | rule state without deleting existing work |
| domus.query_calendar | bounded range and filters | typed scheduled, due and completion entries |
| domus.query_inventory | product/location/low-stock filters, pagination | physical, reserved and available quantities |
| domus.record_stock_movement | product_id, location_id, amount, unit, movement_type, reason | immutable movement; corrections need privilege |
| domus.create_shopping_demand | list_id, product_id or free_text, quantity, unit, semantics | attributable demand_id |
| domus.query_shopping | list/status/source filters, pagination | consolidated lines with demand origins |
| domus.record_purchase | selected demands, purchased quantities, optional session/prices | purchase_id; no implied physical receipt |
| domus.receive_purchase | purchase_id, actual quantities and storage target | receipt_id and stock-posting status |
| domus.query_members | active/member filters | role-appropriate member summaries |
| domus.query_points | member/range/pagination | ledger entries and reconciled totals |
| domus.get_operation | operation_id or own idempotency key | committed, pending, failed or unknown receipt |

These cover initial HA consumer needs. The complete UI may use additional domain API operations;
no future service is claimed implemented by its appearance here.

## Example command and response

Illustrative request to complete a known occurrence; performer selection is a business target,
not the caller's identity:

```json
{
  "instance_id": "example-edge-instance",
  "occurrence_id": "example-occurrence",
  "performer_ids": ["example-member"],
  "expected_revision": 7,
  "idempotency_key": "example-completion-request"
}
```

Illustrative result:

```json
{
  "contract_version": 1,
  "status": "completed",
  "operation_id": "example-operation",
  "data": {
    "occurrence_id": "example-occurrence",
    "revision": 8,
    "completion_id": "example-completion",
    "verification_status": "pending",
    "points_status": "not_awarded"
  },
  "pending": ["verification", "home_assistant_projection"]
}
```

The occurrence result says the work was recorded, not that verification or rewards completed.
Statuses: completed, pending, invalid, denied, conflict, unavailable.
A successful empty query is completed with an empty items array, never unavailable.
Errors include a stable safe code, retryable flag, retained-state description and operation reference when known.
Examples are not live IDs or secrets.

## Bounds and retry behavior

Proposed defaults: 50 records per page, maximum 200; maximum response payload 256 KiB;
maximum 366-day calendar range. Cross-field validation rejects contradictory date forms and units.
Never silently truncate a record; return a cursor, a supported-limit error or a bounded unavailable result.
The final exact limits require acceptance review.

An identical key/payload returns its stored result. Same key/different payload is conflict.
A transport timeout can leave outcome unknown; look up/replay the original key instead of using a new one.
Schemas reject unknown mutation fields. Mutating a stale revision never overwrites newer household work.

## Authorization and automation

A proven HA human context resolves the linked active member role. An automation or missing human context
uses only configured technical grants. A service field cannot assert that the caller is another person.
Domus remains an independent authorization boundary; consuming a service through MCP does not bypass it.
No gateway-client token or per-agent administration is implemented here.

HA can trigger maintenance and replenishment through these commands with stable trigger identity,
cooldown, correlation and loop suppression. Domain effects are deterministic and audited.
Events such as domus_task_completed, domus_inventory_low and domus_operation_updated contain
bounded IDs/revisions and safe metadata, not full private records. Projection updates never retrigger
the same causal automation indefinitely.

## Contract verification

Disposable HA tests verify registration, selectors, response support, UID stability, context mapping,
unload/reconnect and both deployment targets. Native task operations route through the same policies.
Shopping remains read-only in native to-do until purchase/receipt semantics are unambiguous.
Local Chrome dogfooding verifies discoverability and real user flows without changing the gateway.
