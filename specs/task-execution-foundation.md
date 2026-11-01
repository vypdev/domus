# Task Execution Foundation

- Status: Draft
- Date: 2026-10-31
- Catalog capability ID: household-tasks
- Last verified: not applicable (prospective companion; catalog evidence verified at `a63b2315cd5121dde9585ba8875e286fdef5330e`)
- Owners: Domus maintainers (review assignment pending)
- Scope: Specify a durable first backend increment for task definitions, occurrences, completion cycles, authorization, and honest consumer integration seams.
- Related issues/PRs: [Issue #13](https://github.com/vypdev/domus/issues/13); merged PR #12 is historical context.
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: A37 confirms manual manager acceptance; full contract/runtime/composition review remains required. Draft is not acceptance.

## 1. Executive summary

This companion to `specs/household-tasks.md` defines atomic title-only creation, eligible assignment/self-claim, actual performers and durable completion/verification/reopening history. Restricted members may claim eligible available work by default; adult approval remains required. Tasks owns task facts; Inventory and Points own their ledgers.

Example: “Wipe table” creates a definition/occurrence atomically; eligible members claim/perform it; a cycle records performers/time, required approval and uniquely identified consumer events.

The companion preserves all 49 existing cases in `specs/household-tasks.md`; its added cases use the `task-execution-foundation-CNN` namespace. The Action registered both documents under household-tasks in commit d4f3f911dd145d77255f47a882542f08e5c98055. Catalog implementation arrays remain empty at publication: a registered contract is not implementation evidence.

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Task work must survive edits, retries, concurrency, restart and restore. A mutable “completed” flag loses definition/occurrence identity, performers, approval and reopening facts. Restricted members need eligible self-claim with approval intact. Absent Inventory or Points consumers cannot imply accepted effects.

### 2.2 Current behavior

Verified facts at the immutable base:

1. The household-tasks capability is proposed and its existing specification is `specs/household-tasks.md`, with 49 reserved cases `household-tasks-C01` through `household-tasks-C49`.
2. The M1 source includes identity, household, transaction, receipt, outbox, recovery, and offline restoration foundations. It declares task-related permission enums, but no task entities, repositories, commands, or task API.
3. The base catalog lists no task workflows, entrypoints, code or tests; Draft cases confer no implementation evidence.
4. At the pinned base no task routes exist. Later sections define the required two-composition contract.

### 2.3 Evidence

- Code/workflow/documentation references: `specs/catalog.json`; `specs/household-tasks.md`; `docs/architecture.md`; `docs/decisions.md`; `docs/roadmap.md`; `docs/m1-acceptance-audit.md`; `backend/src/domus/application/commands.py`; `backend/src/domus/infrastructure/sqlite.py`.
- Immutable base: commit `a63b2315cd5121dde9585ba8875e286fdef5330e`, tree `60842b62c64c28fe337891344a0eadea1ca8aac5`. Blob identities locate source, not execution support.
- Related issue: https://github.com/vypdev/domus/issues/13. Owner answers on 2026-10-31 authorize checkout/API/lifecycle/material/coverage choices.
- External primary sources: not applicable; product and repository contract evidence is local.
- Unknowns: review assignment, implementation feasibility, actual HA adoption and consumer delivery.

### 2.4 Retrospective classification (as-built baselines only)

Not applicable: this prospective companion claims no implemented task baseline or catalog evidence.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
|---|---|---|---|
| Household adult | Create and manage daily work, approve when required | Existing verified Home Assistant human session; proposed task API | Task views, history, receipt, operation lookup |
| Restricted member | Claim eligible available work, perform assigned work | Same session and task API | Availability, assignment, completion and approval status |
| Administrator | Configure household task policy and privileged values | Existing administrator-authorized command | Policy view and audit history |
| Operator/contributor | Diagnose retained work and integrations | Logs, operations, docs, migration/restore tooling | Sanitized diagnostics and recovery guidance |
| Inventory consumer | Validate and settle task-linked usage in its own domain | Semantic port/event consumer | Actual movement or explicit pending status |
| Points consumer | Consume eligible verified completion facts in its own domain | Durable uniquely identified event | Actual ledger result or no claim of delivery |

**Definition**: reusable task/lifecycle policy. **Occurrence**: work instance/frozen definition. **Completion cycle**: genuine performance with performers, policy, verification and actual time. Assignment, actual performers and recorder differ. **Claim** assigns the current human eligible available work. Performed, recorded, approved and posted times differ. **Task intent** retains cycle-linked usage; Inventory owns stock/movements.

## 4. Goals

| Requirement | Behavior |
|---|---|
| TEF-01 | A title-only create atomically creates a durable definition and one available occurrence; advanced fields stay optional. |
| TEF-02 | Definitions, occurrences, and completion cycles have stable separate identities, revisioned lifecycle, snapshots, and retained history. |
| TEF-03 | Enforce the owning task state machine, expected revisions, scoped acyclic prerequisites, all-required subtasks, and no silent reassignment. |
| TEF-04 | Permit configurable self-claim of eligible available work, including restricted members, with current eligibility, capacity, exceptions, denials, and transaction-time rechecks. |
| TEF-05 | Reuse verified HA human proof, active membership, installation/household/channel binding, semantic authorization and transactional rechecks; policy configuration stays administrator-only and material actions require current grants. |
| TEF-06 | Snapshot actual performers and completion policy; require current authorized-adult approval for any restricted performer, and preserve configured adult-performer approval and independent-adult alternatives. |
| TEF-07 | Preserve actual, recorded, approved, and posted timestamps; make reopening cycle-bound, compensating, revision-aware, and non-cascading. |
| TEF-08 | Retain task-linked material intents and honest outcomes; validate server-owned identities via Inventory ports, never create a second inventory ledger, and settle only through explicit duplicate-safe commands. |
| TEF-09 | Publish durable cycle/source/policy-identified seams for recurrence, Inventory, and Points; reject or retain unavailable integrations truthfully. |
| TEF-10 | Keep Domain pure, orchestration in Application, provider/SQLite mapping in outer adapters, and wire existing compositions through shared services. |
| TEF-11 | Add versioned, guarded SQLite persistence and migration/restart/rollback/restore handling without weakening M1 evidence or duplicate suppression. |
| TEF-12 | Specify bounded task HTTP DTOs and routes for both Python compositions, retaining existing session, proof, Origin, CSRF, outage-write, and authorization rules. |
| TEF-13 | Require complete first-party backend statement and branch coverage from the first source change, strict dependency checks, and meaningful failure/race/recovery evidence. |
| TEF-14 | Document user, setup, operator, and contributor behavior, migration, troubleshooting, and current consumer limitations. |

### 4.1 Goals

1. Deliver a reviewable, testable contract for durable title-only task creation and occurrence execution.
2. Preserve accurate attribution and approval while enabling eligible restricted-member self-claim.
3. Make task state, material status, integration delivery, and recovery facts inspectable without fabricated effects.
4. Ensure every newly authored runtime module is in the measured and enforced backend scope immediately.

### 4.2 Non-goals

1. Complete task UI, recurrence engine, Points ledger, Inventory ledger, HA companion, new gateway/MCP, login, listener, or permission bypass.
2. Claim all-domain, both-deployment-target, Stable/Edge, or first usable release acceptance. Those remain required later integration work.
3. Release, tag, production installation, owner-household mutation, or changes to Copilot’s managed lifecycle.
4. Implement cancellation as a way to bypass required completion validation; cancelled and skipped occurrences are terminal in this increment.

### 4.3 Fixed product/safety invariants

1. No definition edit/archive erases occurrences, cycles, receipts, or history.
2. No task setting can grant approval authority, waive required verification, or turn a technical credential into a human administrator.
3. No absent consumer, fixture, outbox append, or fake port is represented as a delivered ledger effect.
4. No stock movement is fabricated, deleted, or reversed by Tasks; reopening never invents a stock return.
5. Current authorization, installation binding, aggregate revision, and original-cycle identity are rechecked at commit for every mutation.

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User/operator effect |
|---|---|---|---|
| Create | No task command/API evidenced | Title-only create commits definition plus first available occurrence atomically | One simple action produces durable work |
| Find/claim | No task query/claim evidenced | Bounded query; eligible member claims self with expected revision | Assignment is attributable and one concurrent claim wins |
| Perform | No occurrence execution evidenced | Assigned performer completes with actual time and cycle snapshot | Work remains distinct from recording actor |
| Verify | No task verification evidenced | Current adult authority approves/rejects when policy requires | Pending/rejected work earns no points |
| Reopen/integrate | No task events/consumers evidenced | Reopen closes old cycle, emits one compensation event, retains consumer status | No duplicate effect or fabricated ledger result |

```mermaid
flowchart LR
    A[Verified human session] --> B[Create definition and occurrence]
    B --> C[Eligible self-claim or assignment]
    C --> D[Complete cycle with performers]
    D --> E{Verification required?}
    E -->|yes| F[Authorized adult decision]
    E -->|no| G[Verified completion]
    F --> H[Durable uniquely identified consumer event]
    G --> H
```

Text equivalent: verified session -> atomic task creation -> claim/assignment -> recorded completion -> conditional adult approval -> durable consumer event with honest delivery status.

## 6. Functional behavior and state model

### 6.1 Happy path

1. Authorized title-only creation validates title/policy and atomically saves stable definition/occurrence IDs, receipt and outbox. Defaults: active definition, available occurrence.
2. Available-work queries return household records/current actions; cursors bind query/context.
3. Revisioned claim derives the assignee from the actor. Recheck profile availability, capacity, role/profile/member exceptions, explicit denials and policy transactionally.
4. Completion records nonempty actual performers, performed time, effective verification policy, immutable cycle ID and validated material outcomes.
5. Restricted participation requires authorized adult approval. Pending/rejected cycles earn no Points. Approval rechecks current adult/grant, cycle and revision.
6. Events identify occurrence/cycle/source/policy. Real consumers deduplicate their acknowledgements; absent consumers retain truthful pending status.

### 6.2 Alternative paths

- Definition updates/archive affect future work and lifecycle only; existing occurrence and cycle snapshots remain.
- Assignment/release requires an actual nonempty/empty assignee set and explicit task-management authority. On-behalf recording is a separate permission, default adult/admin; a selected member ID grants nothing.
- Rejected work retains its performed facts. Only explicit reopen followed by a genuine later completion creates a new cycle.
- Material usage of zero is `not_used`, with no movement. Valid usage without material authority is retained as `pending_authorization`; shortage is `pending_regularization`; unavailable real Inventory is `pending_processing`.
- Settlement is explicit (`post`, `correct`, `dismiss`) with current authority and reason as applicable. Policy change, approval, stock arrival, or reopening never auto-settles.
- A reopened prerequisite marks completed dependents with a revision-aware review condition; it does not reopen them or reverse their points.
- Recurrence, Points, and Inventory integrations unavailable in the active composition are rejected or retained pending before unsafe effects.

### 6.3 State machine

Definition states: `draft -> active`; `active <-> paused`; `draft|active|paused -> archived`; archived is terminal. Create defaults active. Occurrence states:

| State | Entered when | User-visible meaning | Allowed next states | Recovery/owner |
|---|---|---|---|---|
| draft | Explicit occurrence preparation | Not offered yet | available | Task application publishes after validation |
| available | Initial atomic create or release/unblock without assignees | Eligible to claim/assign | assigned, blocked, completed, cancelled, skipped | Authorized task command; completion requires its separate performer authority |
| assigned | Assignees set | Work has named responsibility | available, in_progress, blocked, completed, cancelled, skipped | Assignment or valid transition |
| in_progress | Assigned work starts | Work underway | blocked, completed, cancelled, skipped | Assigned member or authorized manager |
| blocked | Explicit block or unmet condition | Cannot currently proceed | assigned if assignees remain; otherwise available | Resolve reason and transition |
| completed | Valid completion cycle recorded | Work performed; verification may remain pending/rejected | assigned if assignees remain, otherwise available, only via reopen | Reopen closes current cycle |
| cancelled | Explicit authorized cancellation with reason | This occurrence will not proceed | terminal | Create another occurrence explicitly |
| skipped | Explicit authorized skip with reason | This occurrence was intentionally skipped | terminal | Create another occurrence explicitly |

Completion is not an arbitrary state setter. It validates prerequisites, required subtasks, performers, materials, policy, and verification state. Verification is separate: `none`, `pending`, `approved`, `rejected`. Reopening requires current completed cycle ID and revision, closes that cycle, retains facts, and returns to assigned if assignees remain, otherwise available.

Every mutation requires expected revision. Existing receipt replay occurs after current authorization of the original command and before stale revision rejection: identical key/payload returns original outcome; changed payload conflicts. Fresh-key duplicate completion/approval cannot add cycles/events. Closed-cycle or stale events are inert or conflict. Reopen emits one compensating source event and does not reverse actual stock movements.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| claim_allowed | boolean | true for eligible available work | true/false | Household default, task override; reread at claim commit |
| dependency_gate | enum | performed | performed or approved | Household default and authorized task override; snapshotted per cycle |
| eligible_roles | unique Role list | administrator, adult, restricted | bounded known roles | Household/task; reread at commit with member exceptions |
| verification | enum | role_default | `role_default`, `authorized_adult` | Definition snapshot per completion cycle |
| adult_performer_may_approve | boolean | true | true/false | Household/task; effective value snapshotted; current approval authority rechecked |
| task_scoped_material_consumption | boolean | true | true/false | Household/task; explicit applicable member denial takes precedence |
| material_recording | enum | `review_on_completion` | `review_on_completion`, `separate_recording` | Household/task; snapshot by cycle |
| point_value_minor | integer | 0 | 0..1,000,000 | Administrator-controlled definition value; snapshot; no award without consumer |
| materials | list | empty | Up to 32 server-owned line references with Inventory-validated quantities | Definition snapshot; identity and target cannot be client-forged |
| title/description/tags/priority | bounded text/list/enum | Required title; empty description/tags; normal priority | title 1..160; description 0..4000; up to 16 unique tags, each <=64; low/normal/high/urgent | Definition; updates revisioned |

Policy PUT is administrator-controlled. Cross-field validation rejects unknown roles/values, duplicate tags/IDs, foreign material lines, invalid quantities, unbounded lists, and unsupported providers. Unknown future persisted enum values fail closed and remain inspectable for migration; absent fields receive documented defaults only in migration. No arbitrary URLs, code, refs, secrets, product IDs, units, or locations are accepted. Recommended configuration enables eligible self-claim with adult verification for restricted performers. A meaningful alternative disables self-claim for a household while retaining adult-managed assignment. No configuration can weaken human proof, current authorization, revision checks, performer attribution, or consumer ownership.

### Executable policy refinements before implementation

Publish Draft/planned leaves before code; declarations confer no execution credit. Use exact enums/booleans, valid UTF-8, bounded unique tuples, positive signed-64-bit revisions/nonnegative UTC milliseconds. Reject U+0000..001F/U+007F except tab/LF/CR in multiline text. Initial definitions are draft/active; pause/archive stops new work and retains history.

Add tasks.read/claim/manage/record_for_others/material_use; retain create/complete/approve/configure. All profiles read. Administrator/adult/restricted profiles claim eligible work/use linked materials; administrator/adult profiles manage/record for others. Viewer mutations default denied. Household/profile/member precedence applies. Claim never waives restricted assignment/self-participation. Configuration is administrator-only; approval needs a current adult/grant. Technical credentials never grant human authority.

Recheck active membership, mapping and grants transactionally. HA proof is actor-only; other performers retain local profiles. Snapshots grant nothing.

Verify human proof before writing. Create atomically saves absent defaults, active/available or explicit draft pair, receipt/audit/outbox. Overrides need create/configuration grants on execution/replay. Management assigns up to 32 distinct active members; empty releases work. Self-claim derives one eligible actor on available/unassigned work, with one concurrent winner. Authority precedes receipt disclosure, then state/revision checks. Events do not confirm consumers.

Completion checks assignment/self-attribution/on-behalf grants before disclosure, then active performers, defaults/frozen overrides, required work and policy revisions. Approval needs current adult authority before cycle/pointer/revision/participation checks. Assignees start/block/unblock; management publishes/cancels/skips/reopens. Completion commits cycle/work/event atomically. Reopen closes the cycle/emits causes; ledgers and review remain separate.

Administrator policy replacement uses zero for absent defaults, positive revision for updates. Definition edits preserve omitted overrides; replacement/reset needs configuration on execution/replay. Future snapshots alone change. New work uses current active definition, up to 32 active assignees/32 IDs per dependency list; paused/archived parents reject. Management edits nonterminal dependencies, validating all graph pages and retaining IDs in results/events. Stale/foreign/cyclic changes roll back.

Owner A34 (2026-11-01) confirms the performed prerequisite default and configurable approved alternative below; point availability remains approval-gated.

Nullable overrides inherit current defaults; false, zero and empty role sets are real values. Occurrences freeze definition/content/overrides; completion freezes resolved rules/source revisions, retaining pending-cycle policy. Draft work is unassigned; active parents produce available/assigned work; paused/archived parents retain history without new occurrences.

Scoped definition/occurrence/cycle IDs, signed-64-bit positive revisions and supplied times are stable. Performed <= recorded <= verified/closed; closing cannot predate verification. Approval leaves the cycle open; only reopening closes it. Completed work requires a matching current cycle pointer/revision; other states cannot retain one. Scope and definition snapshot revisions must agree. Closing retains material identities, facts and attribution.

Completion owns its resolved dependency gate; callers cannot weaken it. Both modes require completed work and reject rejected verification. Approved accepts none/approved; performed also accepts pending. Use the exact required set. Each prerequisite/subtask list permits 32 IDs, 64 deduplicated combined edges. Iterative DAG checking avoids Python recursion limits.

Reads recheck grants transactionally without creating defaults. Pages default to 25/max 100. Five-minute signed cursors bind actor/installation/channel/household/query/filters/limit, grant no snapshot/write authority and may expire on restart. Hints use current grants/state. History marks restoration, hides HA identities/requests and separates outbox acknowledgement from consumers. Own receipt reads recheck original authority. Shared readers unify facts.

### Material value and processor contract

Canonical quantities are nonnegative strings: max 12 integer/6 fractional digits; no sign, exponent, leading/trailing zero aliases; zero is "0". Inventory owns binding targets/revisions and unit precision 0..6. Resolve selected references through current household Inventory semantics; Tasks generates stable line IDs. Usage cannot substitute targets. Lists allow 32 unique references/line IDs.

Intent source quantity, cycle/time, recorder, binding/line snapshot, mode and initial authority fact are immutable. Missing actual quantity is pending_recording; explicit zero is not_used without a movement request. Separate recording needs explicit settlement. Missing authority/stock/Inventory yields pending_authorization/regularization/processing. Grants, approval, stock arrival and reopen never auto-settle.

Resource revision guards edits; an independent effect revision changes only with corrected desired quantity. Its source key stays stable through pending retries and current actor changes. Posted/corrected state needs matching actual Inventory confirmation, including source scope, quantity, effect revision, movement/operation IDs and time. Correction preserves submitted quantity and the last confirmed effect until Inventory confirms the requested total; Tasks never compute stock deltas. Returning a pending correction to the already confirmed quantity needs no new movement. Dismiss cannot erase a confirmed effect. Exact confirmation replay is inert; stale/foreign confirmations cannot overwrite later intent state. All transitions validate supplied monotone time and revision exhaustion.

The processor uses transaction-local Inventory/current-authority ports and reauthorizes explicit post/correct/dismiss. Owner decision: any currently authorized material participant may correct confirmed consumption; preserve the original movement and require Inventory confirmation of the new total. Completion retains ordinary denied usage. Pending certifies no new movement; absence never confirms stock. Fixtures alone establish no consumer acceptance.

Create/update uses `materials`; completion uses `material_usages`. Omitted/null new fields remain absent canonically, preserving old fingerprints; explicit [] differs. Use canonical strings. Linking/replacement/clear needs task create/manage and inventory.manage. Scoped use needs tasks.material_use, current performance authority and scoped policy, or general Inventory authority; prior grants authorize nothing. Validate usage IDs/precision before work effects. Save one intent per frozen line (missing actual remains unknown) and every CAS with work/receipt/audit/outbox. Provider absence retains pending processing; approval/replay/reopen never retries it. Ledger acceptance is separate.

Settlement targets the original cycle/intent, including closed cycles; expected_revision guards the intent. Only correct accepts quantity; correct/dismiss require a reason (max 1000). All actions use current A36 material grants. Before receipt disclosure validate server-recorded source selectors/performers against immutable evidence and current work; snapshots grant nothing. Historical retry may recover absent intent/cycle facts without recreating effects; missing current work denies access. New actions require valid live sources. Correction stages each single-step CAS before Inventory confirmation; final intent/receipt/audit/event commit together. Work/cycle revisions stay unchanged. History labels original settlement action/reason separately from current material state.

### Dependency review projection

Derive causes from live complete/reopen evidence, never a second ledger. Reopen follows dependent completion and precedes its closure by outbox position; timestamps may tie. Freeze dependency lists/gate, deduplicate overlapping links, bind cause to dependent cycle/source event/revisions and exclude restored-away effects. Validate coherent evidence/current typed cycles. Reads show current source state/verification/satisfaction separately. Use one authorized transaction, pages 25/max100 and signed context cursors. A37: current tasks.manage may accept a cause with a meaningful reason even while source is pending; preserve its visible condition. Acknowledgement is atomic original evidence, cause revision 1 to 2; retries reauthorize before disclosure, and old acceptance never clears a later cause. No work/cycle/points/material mutation or automatic closure.

### Lifecycle source for consumers

Trusted runtimes expose an internal read-only typed feed (25/default, 100/max) by live event position, including transport-acknowledged rows but excluding restored-away effects. Validate paired evidence and typed work/cycles; retain original completion/verification/reopening snapshots and definition/cycle/policy/time identities. Source keys bind installation/channel/household/event; stable cycle keys exclude event/policy revision. Pending/rejected work is not award-eligible; rejection/reopening closes eligibility. Consumers own durable inbox/closure/allocation and actual confirmation. Reads never acknowledge, settle or claim delivery, create no HTTP/login surface, and share semantics in both runtimes; absent consumer wiring stays unconfirmed.

### HTTP contract

Both business compositions expose shared services under `/api/v1/tasks`. Mutations require current session/proof, Origin, CSRF, `Idempotency-Key`, and `expected_revision` (`0` create, positive update). Household, actor, installation, and channel derive server-side. Reject unknown fields. Lists use limit default 25, max 100, cursor max 512; keyset cursors bind query/context without cross-page snapshot guarantees.

| Method and route | Request contract |
|---|---|
| GET, PUT `/api/v1/tasks/policy` | GET policy; PUT bounded booleans/roles/default verification/material recording/dependency_gate, administrator only |
| GET, POST `/api/v1/tasks/definitions` | Filter state; create title (1..160), optional description, priority, tags, state, point value, verification, approval/material/claim settings, roles, material recording, dependency_gate, and up to 32 server-validated material lines. Title-only create creates one available occurrence atomically. |
| GET, PUT `/api/v1/tasks/definitions/{id}` | GET definition; revisioned PUT editable definition fields; lifecycle rules enforced |
| POST `/api/v1/tasks/definitions/{id}/occurrences` | Create occurrence with expected revision 0, assignee/prerequisite/required-subtask ID lists (each unique, max 32), optional UTC millisecond due time |
| GET `/api/v1/tasks/occurrences` | Filter only by state, assignee_id, definition_id; bounded pagination |
| GET `/api/v1/tasks/occurrences/{id}` | Current occurrence, snapshots, allowed actions, current cycle and outcomes |
| GET `/api/v1/tasks/occurrences/{id}/materials` | Required original cycle_id; current outcomes for that scoped open/closed cycle, at most 32 in frozen line order; never replay a receipt as current state |
| GET `/api/v1/tasks/occurrences/{id}/dependency-reviews` | Required original cycle_id, limit/cursor, optional pending/reviewed filter (default all); detail previews pending current-cycle causes |
| POST `/api/v1/tasks/occurrences/{id}/dependency-reviews/{source_operation_id}/acknowledgement` | Original cycle_id, cause expected_revision, nonblank reason <=1000; current task management required |
| PUT `/api/v1/tasks/occurrences/{id}/assignment` | Replace assignee IDs; explicit authority and revision |
| PUT `/api/v1/tasks/occurrences/{id}/dependencies` | Replace prerequisite and required-subtask IDs; validate scope, acyclicity, and revision |
| POST `/api/v1/tasks/occurrences/{id}/claim` | Revision only; claimant derived from authenticated actor |
| POST `/api/v1/tasks/occurrences/{id}/transition` | Revision, target, reason <=1000; reason required for cancel/skip/block decisions as policy specifies |
| POST `/api/v1/tasks/occurrences/{id}/complete` | Revision, nonempty unique performer IDs (max 32), UTC ms performed_at, up to 32 material usages `{line_id, quantity}`; quantity canonical nonnegative decimal string, never float |
| POST `/api/v1/tasks/occurrences/{id}/verify` | Revision, cycle_id, approve/reject, reason; reject requires nonblank reason |
| POST `/api/v1/tasks/occurrences/{id}/reopen` | Revision, cycle_id, nonblank reason |
| GET `/api/v1/tasks/operations/{id}` | Own receipt with original authority rechecked; delivery names refer only to outbox acknowledgement |
| GET `/api/v1/tasks/occurrences/{id}/history` | Chronological safe history with event ID, revision, actor, time, action, safe detail |
| POST `/api/v1/tasks/occurrences/{id}/materials/{intent_id}/settlement` | Revision, original cycle_id, action post/correct/dismiss, quantity only for correction, required reason for correction/dismissal |

Wire bodies use top-level content, nested overrides/rules and strict IDs. Omitted/null update overrides preserve; an empty object resets inheritance. Create defaults revision to zero. Unavailable Inventory linking fails before writes; completion retains pending usage. Only business compositions expose tasks. Native GET queries retain bounded, nonduplicate pairs and header/peer policy. Material reads recheck tasks.read and frozen lines/cycle/recorder/time/mode; corrupted references fail closed. Live views distinguish desired quantity from confirmed_quantity, confirmed_effect_revision and posted_at; receipt outcomes remain immutable.

Use existing ReceiptResponse/OperationResponse/ErrorResponse. Immutable receipts retain resource/cycle/revision/material facts, never grants. Reads expose IDs/revisions/states/snapshots/action hints, assignees/dependencies/performers/times/verification and material outcomes. Outcomes carry intent/cycle/line IDs, submitted canonical quantity, status/reason/message/action, nullable actual movement and revision. Posted needs Inventory confirmation; forged/foreign usage fails before effects, valid pending work survives. Current settlement and original result stay distinct.

## 8. Clean Architecture

### 8.1 Responsibilities and dependency direction

| Layer/boundary | Owns | Must not own/import |
|---|---|---|
| Domain/pure policy | Definition/occurrence/cycle value objects, transitions, dependency graph, eligibility and verification decisions | SQL, HA/HTTP/DOM, global clock or entropy |
| Application | Authorized commands/queries, immutable DTOs, receipts, transaction orchestration, semantic ports | Concrete SDK/process details or provider DTOs |
| Adapters/data | SQLite schema/repository, migration, provider mapping and error conversion | Product authorization policy |
| Infrastructure/composition | Existing native and standalone wiring; shared services in both Python compositions | Duplicated business rules |
| Entrypoints | HTTP parsing, proof/session/Origin/CSRF adaptation | Independent orchestration or client-selected authority |
| Presentation | Task view models, allowed-action display, sanitized history | Mutations or state transitions |
| Consumers | Inventory stock/unit/movement/reservation; Points ledger; recurrence scheduling | Tasks-owned facts or claims of delivery without acknowledgement |

```mermaid
flowchart LR
    H[HTTP entrypoints in two compositions] --> A[Shared application commands and queries]
    A --> D[Pure task domain]
    A --> P[Semantic Inventory and event ports]
    S[SQLite adapter and migrations] --> P
    A --> R[Receipt and transactional outbox boundary]
    I[Real Inventory/Points consumers] --> R
```

Text equivalent: both HTTP compositions call shared Application services; Application uses pure Domain policy and semantic ports; SQLite and actual consumers implement outer boundaries.

### 8.2 Contracts, state, and trust boundaries

- Pure decisions cover transitions, required work, claim, performers/verification and material outcomes.
- Bounded commands/queries retain expected revision, key, immutable receipt, operation/history and current action hints.
- Semantic repository/UOW, authorization, material resolution/settlement, event acknowledgement, clock and IDs cross boundaries.
- Tasks owns definitions/snapshots/cycles/history/intents/receipts/event identity; Inventory owns stock/movements; Points owns awards.
- One SQLite writer rechecks authority/revision. Unique receipts/events/cycles/child intents and CAS give claim one winner; losers conflict without reassignment.
- Bodies, IDs, comments, imports/restores, provider data and events are untrusted. Verified context binds actor/household/installation/channel; selected performers need on-behalf authority.
- Distinguish invalid/foreign, denied, conflict/stale, unavailable and internal failures. Only otherwise valid work may retain safe pending outcomes.

### 8.3 Executable architecture constraints

Declare runtime leaves before code. Cover every authored file, including composition/HTTP/migration/restore/unimported modules, and check dependencies/cycles. Domain stays pure, Application semantic, providers/SQLite outer, services shared. Validate generated schema/OpenAPI routes/fields. All CI Check groups run per PR commit; Copilot stays immutable.

## 9. UI/UX and content contract

### 9.1 Information hierarchy

Task screens and operation/issue/PR status show current state, retained completed facts, next transition, required human action, impact, inspectable history/receipt, then technical details. One primary action is shown at a time. Material pending state must never resemble posted stock or earned points.

### 9.2 Representative primary view

```markdown
# Task complete: Wipe table

> **Current status:** Work recorded; adult approval required.
>
> **Action required:** An authorized adult reviews this completion.

## Progress

- [x] Mina claimed the available task.
- [x] Mina recorded the work at 18:10.
- [ ] Adult approval is pending.

## What happens next

Approval will make the completion eligible for the configured Points consumer. No points have been posted yet.

## Links

[Task history](.../api/v1/tasks/occurrences/occ_123/history) · [Operation receipt](...)

<details>
<summary>Technical details</summary>
Cycle cyc_456; revision 4; material usage pending authorization; no inventory movement exists.
</details>
```

Concrete state variants:

**Pending/no action:** “Wipe table — Saved, awaiting scheduled adult review. No action required from you.”

**Action required:** “Wipe table — Adult approval needed. Mina's work is saved; points are not eligible. Review cycle cyc_456 in history.”

**Blocked before effect:** “Claim not made — Task changed. Assignment is unchanged. Refresh and retry if still available.”

**Partial success:** “Work saved; materials pending — Inventory is unavailable; no movement exists. An authorized operator can inspect and explicitly retry when available.”

**Completed:** “Wipe table — Work/approval recorded. Points delivery is separate and requires real consumer confirmation.” Approval leaves the cycle open; reopening closes it.

### 9.3 Issue, PR, and comment behavior

- Deterministic issue/PR title describes task-execution-foundation contract; PR summaries link Issue #13, exact managed branch, companion, CI run, and review evidence.
- Merge validates/publishes the companion and exact linked branch before implementation begins; this is a workflow gate, not evidence of runtime support. Merge/close does not imply consumer delivery.
- Durable operation/event IDs and receipts are idempotent. Repeated status refresh edits the existing marker; no comment per retry. Budget: at most one initial summary and one material state-change comment per operation; routine pending refreshes add none.
- Labels/checks supplement rendered status and never replace required action or retained facts.

### 9.4 Accessibility, localization, and responsive behavior

Issues/docs/code are English; owner communication is Spanish. Owner-confirmed UI locales are EN/ES with English fallback. Status/icons/diagrams have text equivalents. Keep narrow tables, sequential headings, descriptive links and token-based light/dark contrast. Treat titles/descriptions/tags/reasons/imports/URLs as untrusted Markdown; escape HTML/mentions, forbid executable commands/embedded HTML and never trust arbitrary provider links.

## 10. Failure, recovery, and cleanup

| Failure/partial state | User impact | Retained facts | Automatic retry | Required action | Cleanup |
|---|---|---|---|---|---|
| Stale claim/transition | Requested change not applied | Current revision and prior assignment | No | Refresh and decide again | None |
| Identical command replay | Original result returned | Immutable receipt | Safe bounded replay | None | Receipt retention follows existing operation policy |
| Same key, changed payload | Conflict; no second effect | Original receipt | No | Use a new key only for a genuinely new command | None |
| Claim race | One winner; loser unchanged | Winner assignment and loser conflict | No blind retry | Refresh | None |
| SQLite/migration rollback | Command not partially visible | Prior committed state | Bounded infrastructure retry only | Operator sees failure if unavailable | Preserve backup and migration diagnostics |
| Missing material authority | Work may still save; usage visibly pending | Cycle and intent, no movement | No automatic settlement | Authorized user explicitly settles after recheck | Retain audit record |
| Inventory shortage | Work saved; usage pending regularization | Intent and shortage result | No automatic stock mutation | Regularize via Inventory then explicit settlement | Never create negative movement |
| Consumer unavailable | No delivery claim | Outbox/intent and pending status | Bounded consumer retry with dedupe | Operator inspects after threshold | Keep event identity until resolved |
| Reopened prerequisite | Dependent completion remains | Review condition and revisions | No cascade | Human reviews dependent | No automatic reopen or compensation |
| Restore of prior snapshot | Older state may return | Snapshot and duplicate-suppression facts validated | No unsafe replay | Resolve restore validation failure | Preserve historical fixture identities |

Errors follow impact -> cause -> action -> retained state. A committed task completion is never reported as wholly failed because a downstream consumer is pending.

## 11. Security, permissions, and privacy

1. Reuse current verified HA human proof, active membership, and installation/household/channel binding. Recheck semantic authorization inside the writer transaction for every mutation.
2. Restricted members may claim eligible available work for themselves by default; configurable household/task. Commit checks current eligibility, capacity, role/profile/member exceptions and applicable denials. The actor is server-derived. Claim only assigns that actor; it does not grant approval or unrelated permissions.
3. Adults handle daily task operations. Administrator-only controls include verification defaults, point value, and material-authority policy. Any restricted actual performer requires current authorized-adult approval. Adult performer approval is allowed by default; configured independent-adult alternatives apply. Approval authority is independent of settlement authority.
4. Recording another person’s work, reassignment, cancel/skip, and reopen require explicit task-management/on-behalf authority, default adult/admin. A chosen member ID never proves authority. Restricted completion attribution must include its own participation where required; omission cannot evade verification.
5. Bind all IDs and events to installation, household, occurrence, cycle, source, and policy. Reject forged/foreign resources and malformed quantities before effects. Protect replay through idempotency receipts, revisions, uniqueness, and consumer inbox fences.
6. Store only necessary task/actor facts. Logs and safe history omit credentials, proof tokens, and sensitive provider payloads. Retain auditable actor, action, time, and outcome under existing retention policy.

## 12. Observability and operational UX

- User-facing state distinguishes occurrence status, verification, material intent, and consumer delivery.
- Operator evidence includes correlation/operation ID, task/occurrence/cycle IDs, revision, event ID, safe reason code, and consumer status; never secrets.
- Metrics: command outcomes by bounded action/result, stale/conflict and claim-race counts, pending age by consumer/status, migration/restore validation failures, and dedupe hits. Avoid household/member labels in aggregate metrics.
- Consumer pending is not task-command failure. Unavailable composition reports pending or explicit unsupported integration before unsafe effects.
- Retry only idempotent commands/events with bounded backoff and stable IDs. No comment storm; the section 9 budget applies.

## 13. Compatibility, migration, rollout, and rollback

- Preserve M1 household, identity, recovery, generation, inbox/outbox, and operation history. Frozen old-schema fixtures and historical evidence identities remain unchanged.
- Schema 5 adds typed tasks/scoped cycle keys; 6 adds materials and explicit task-document migration. Schema 7 adds cycle-event/source-reopen indexes, without rewriting business/history rows. Preserve frozen 1–6 inputs; migration/rollback is atomic and old snapshots remain inspectable. Validate canonical bounded references, graphs, foreign keys and revisions. Original v6 comes from immutable 7beb63c, with a completed dependent after reopening and restored-away material settlement; readers derive its causes without fabricated backfill events.
- Snapshot inspection, restore, resume, and rollback validate new task records and duplicate-suppression facts, including operations processed before restoration. Invalid snapshots fail closed; do not weaken existing semantic checks.
- No old task rows are assumed. Unknown future enum/schema versions are retained and reported, not coerced into permissive values. Backfill only when evidence establishes a safe mapping.
- Rollout follows companion publication, then implementation behind existing composition/wiring controls, then real consumer and HA acceptance. No release or production install is part of this specification.
- Rollback may disable task entrypoints while preserving committed task history/receipts. It must not delete ledger effects or replay already processed events. Any irreversible consumer effect is corrected by its owning domain.

## 14. Testing strategy

The 42 planned cases belong only to this companion; the 49 baseline task cases stay unchanged/uncredited. IDs are not execution evidence. Pin pytest 9.2.0, pytest-cov 7.1.0 and Coverage.py from uv.lock. Require 100% statements/lines and branches, zero misses, globally/per authored file, including new/unimported runtime, composition, HTTP, migration and restore. No unsupported function metric, exclusions, pragmas or denominator narrowing. Audit JSON against exact source inventory. All existing CI groups/aggregate and complete current-head full-context Bugbot without findings gate each commit.

Use exhaustive pure tables, deterministic clocks/IDs, real SQLite temp files and controlled races, without live waits/services. Label fakes; separate loopback/SQLite from consumer/owner adoption. Goldens assert action, retained facts, links, escaping and state. Human review covers mobile/narrow readability, light/dark contrast and Spanish owner communication. Rows below are the full new inventory.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Domain/configuration/pure planning | 14 | Observable scenarios in the case inventory. |
| State/application/idempotency/races | 18 | Observable scenarios in the case inventory. |
| Adapters/provider contracts | 4 | Observable scenarios in the case inventory. |
| Workflows/permissions/schemas/setup | 3 | Observable scenarios in the case inventory. |
| UI/UX/localization/sanitization | 2 | Observable scenarios in the case inventory. |
| Integration/security/migration | 1 | Observable scenarios in the case inventory. |
| Total | 42 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| task-execution-foundation-C01 | Domain/configuration/pure planning | TEF-01, TEF-02 | Title-only create plan yields distinct stable definition and occurrence identities with active/available defaults. |
| task-execution-foundation-C02 | Domain/configuration/pure planning | TEF-01 | Boundary title lengths 1 and 160 pass; empty and 161-character titles fail. |
| task-execution-foundation-C03 | Domain/configuration/pure planning | TEF-02 | Definition archive preserves occurrence snapshot and cycle history. |
| task-execution-foundation-C04 | Domain/configuration/pure planning | TEF-03 | Each permitted definition transition succeeds and archived definition is terminal. |
| task-execution-foundation-C05 | Domain/configuration/pure planning | TEF-03 | Each occurrence transition follows the specified graph; arbitrary completion setter is rejected. |
| task-execution-foundation-C06 | Domain/configuration/pure planning | TEF-03 | Cross-household, self-referential, and cyclic prerequisites fail; valid scoped DAG passes. |
| task-execution-foundation-C07 | Domain/configuration/pure planning | TEF-03 | Required subtasks must all be complete before parent completion. |
| task-execution-foundation-C08 | Domain/configuration/pure planning | TEF-04 | Eligible restricted member can claim available profile-matched work under enabled default. |
| task-execution-foundation-C09 | Domain/configuration/pure planning | TEF-04 | Disabled claim policy, role mismatch, capacity, profile exception, and explicit denial each prevent claim. |
| task-execution-foundation-C10 | Domain/configuration/pure planning | TEF-06 | Restricted performer requires approval regardless of actor omission or task approval setting. |
| task-execution-foundation-C11 | Domain/configuration/pure planning | TEF-06 | Adult performer approval default and configured independent-adult alternative resolve correctly. |
| task-execution-foundation-C12 | Domain/configuration/pure planning | TEF-08 | Zero material quantity maps to not_used and produces no movement intent. |
| task-execution-foundation-C13 | Domain/configuration/pure planning | TEF-08 | Material outcomes distinguish pending_authorization, pending_regularization, pending_processing, posted, corrected, and dismissed. |
| task-execution-foundation-C14 | Domain/configuration/pure planning | TEF-07 | Reopened prerequisite produces revision-aware dependent review condition without cascading state change. |
| task-execution-foundation-C15 | State/application/idempotency/races | TEF-01, TEF-11 | Atomic title-only create commits definition, first occurrence, receipt, and event together. |
| task-execution-foundation-C16 | State/application/idempotency/races | TEF-01, TEF-11 | Injected failure between writes rolls back every part of create. |
| task-execution-foundation-C17 | State/application/idempotency/races | TEF-04 | Concurrent self-claims have exactly one winner and no silent reassignment. |
| task-execution-foundation-C18 | State/application/idempotency/races | TEF-03, TEF-05 | Stale revision and revoked authority are rechecked at commit and cause no mutation. |
| task-execution-foundation-C19 | State/application/idempotency/races | TEF-03 | Assignment, dependencies, transition and completion reject stale revision. |
| task-execution-foundation-C20 | State/application/idempotency/races | TEF-05 | Client-selected claimant or on-behalf performer without separate authority is rejected. |
| task-execution-foundation-C21 | State/application/idempotency/races | TEF-06 | Completion snapshots actual performers and effective policy while recording actor separately. |
| task-execution-foundation-C22 | State/application/idempotency/races | TEF-06 | Pending/rejected verification awards no points event; approval rechecks current adult authority. |
| task-execution-foundation-C23 | State/application/idempotency/races | TEF-06, TEF-07 | Old closed cycle cannot approve, complete, or reward a later cycle. |
| task-execution-foundation-C24 | State/application/idempotency/races | TEF-07 | Reopen closes current cycle, retains facts, and emits exactly one compensating source event. |
| task-execution-foundation-C25 | State/application/idempotency/races | TEF-07 | Stale/replayed reopen or event cannot duplicate compensation or reintroduce resolved warning. |
| task-execution-foundation-C26 | State/application/idempotency/races | TEF-08 | Valid completion with missing material authority commits work and retains visible unposted usage. |
| task-execution-foundation-C27 | State/application/idempotency/races | TEF-08 | Shortage leaves pending regularization and creates no negative stock movement. |
| task-execution-foundation-C28 | State/application/idempotency/races | TEF-08 | Settlement replay and concurrent settlement produce one stable child outcome. |
| task-execution-foundation-C29 | State/application/idempotency/races | TEF-08 | Grant, approval, stock arrival, or reopen does not auto-settle a retained intent. |
| task-execution-foundation-C30 | State/application/idempotency/races | TEF-09 | Unavailable recurrence/Inventory/Points composition rejects unsafe input or retains truthful pending state. |
| task-execution-foundation-C31 | State/application/idempotency/races | TEF-11 | Restart retains state, receipts, event IDs, revisions, cycles, and duplicate suppression. |
| task-execution-foundation-C32 | State/application/idempotency/races | TEF-11 | Restore validates pre-snapshot processed operation facts and rejects semantic inconsistency. |
| task-execution-foundation-C33 | Adapters/provider contracts | TEF-08 | Inventory adapter validates server-owned line identity and canonical decimal quantity, rejects foreign target. |
| task-execution-foundation-C34 | Adapters/provider contracts | TEF-08, TEF-09 | Inventory unavailable maps to pending_processing without claimed movement. |
| task-execution-foundation-C35 | Adapters/provider contracts | TEF-09 | Event adapter carries stable source, cycle, policy, and dedupe identities. |
| task-execution-foundation-C36 | Adapters/provider contracts | TEF-11 | SQLite uniqueness, foreign-key, revision, and migration constraints reject invalid records. |
| task-execution-foundation-C37 | Workflows/permissions/schemas/setup | TEF-12 | Both Python compositions expose the specified routes through the same application services. |
| task-execution-foundation-C38 | Workflows/permissions/schemas/setup | TEF-12 | DTO parser enforces bounds, rejects extra fields, and expands every route in OpenAPI. |
| task-execution-foundation-C39 | Workflows/permissions/schemas/setup | TEF-12 | Existing session/proof, household binding, Origin, CSRF, and outage-write guards apply. |
| task-execution-foundation-C40 | UI/UX/localization/sanitization | TEF-14 | Pending, action-required, blocked, partial, and completed renderings show next action and retained facts. |
| task-execution-foundation-C41 | UI/UX/localization/sanitization | TEF-14 | Untrusted task text, mentions, HTML, commands, and URLs are rendered safely with descriptive links. |
| task-execution-foundation-C42 | Integration/security/migration | TEF-05, TEF-10, TEF-13 | Full dependency graph has no inward violations/cycles and every authored module passes 100% line and branch audit. |

## 15. Documentation and discoverability

| Path | Change |
|---|---|
| `specs/task-execution-foundation.md` | create |
| `specs/household-tasks.md` | update |
| `specs/catalog.json` | update |
| `specs/CATALOG.md` | update |
| `specs/_template.md` | reference |
| `README.md` | update |
| `docs/architecture.md` | update |
| `docs/decisions.md` | update |
| `docs/roadmap.md` | update |
| `docs/m1-acceptance-audit.md` | reference |
| `docs/product-vision.md` | reference |
| `docs/operations.md` | reference |
| `docs/user-guide.md` | update |
| `docs/contracts/home-assistant.md` | reference |
| `backend/src/domus/application/commands.py` | reference |
| `backend/src/domus/infrastructure/sqlite.py` | update |
| `docs/tasks/execution.md` | create |
| `docs/tasks/operator-recovery.md` | create |
| `docs/tasks/migration.md` | create |
| `backend/src/domus/domain/task_values.py` | create |
| `backend/src/domus/domain/task_policy.py` | create |
| `backend/src/domus/domain/tasks.py` | create |
| `backend/src/domus/application/task_ports.py` | create |
| `backend/src/domus/application/task_authorization.py` | create |
| `backend/src/domus/application/task_commands.py` | create |
| `backend/src/domus/application/task_requests.py` | create |
| `backend/src/domus/application/task_queries.py` | create |
| `backend/src/domus/application/task_facts.py` | create |
| `backend/src/domus/domain/task_events.py` | create |
| `backend/src/domus/application/task_events.py` | create |
| `tests/backend/test_task_events.py` | create |
| `tests/backend/test_sqlite_task_events.py` | create |
| `backend/src/domus/domain/task_reviews.py` | create |
| `backend/src/domus/application/task_reviews.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_reviews.py` | create |
| `tests/backend/test_task_reviews.py` | create |
| `tests/backend/test_sqlite_task_reviews.py` | create |
| `tests/fixtures/sqlite/v6.sql` | create |
| `backend/src/domus/domain/task_material_values.py` | create |
| `backend/src/domus/domain/task_materials.py` | create |
| `backend/src/domus/domain/task_material_policy.py` | create |
| `backend/src/domus/application/task_material_views.py` | create |
| `tests/backend/test_task_material_queries.py` | create |
| `tests/backend/test_task_material_http.py` | create |
| `backend/src/domus/domain/errors.py` | update |
| `backend/src/domus/application/task_material_ports.py` | create |
| `tests/backend/test_task_material_values.py` | create |
| `backend/src/domus/application/task_materials.py` | create |
| `backend/src/domus/application/task_material_commands.py` | create |
| `backend/src/domus/application/task_material_scope.py` | create |
| `tests/backend/test_task_material_settlement.py` | create |
| `tests/backend/test_task_material_commands.py` | create |
| `backend/src/domus/infrastructure/sqlite_tasks.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_records.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_schema.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_integrity.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_history.py` | create |
| `backend/src/domus/infrastructure/task_materials.py` | create |
| `backend/src/domus/infrastructure/task_cursor.py` | create |
| `backend/src/domus/entrypoints/task_http.py` | create |
| `backend/src/domus/entrypoints/task_dto.py` | create |
| `backend/src/domus/entrypoints/task_response.py` | create |
| `backend/src/domus/entrypoints/http_errors.py` | update |
| `backend/src/domus/composition/tasks.py` | create |
| `tests/backend/test_task_values.py` | create |
| `tests/backend/test_task_policy.py` | create |
| `tests/backend/test_tasks.py` | create |
| `tests/backend/test_task_authorization.py` | create |
| `tests/backend/test_task_commands.py` | create |
| `tests/backend/test_task_execution_commands.py` | create |
| `tests/backend/test_task_edit_commands.py` | create |
| `tests/backend/test_task_queries.py` | create |
| `tests/backend/test_task_cursor.py` | create |
| `tests/backend/test_sqlite_task_history.py` | create |
| `tests/backend/test_task_materials.py` | create |
| `tests/backend/test_sqlite_tasks.py` | create |
| `tests/backend/test_sqlite_task_records.py` | create |
| `tests/fixtures/sqlite/v4.sql` | create |
| `tests/fixtures/sqlite/v5.sql` | create |
| `backend/src/domus/infrastructure/sqlite_task_material_schema.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_material_records.py` | create |
| `backend/src/domus/infrastructure/sqlite_task_materials.py` | create |
| `tests/backend/test_sqlite_task_materials.py` | create |
| `tests/backend/test_restore_source.py` | update |
| `tests/backend/test_activation_compatibility.py` | update |
| `tests/backend/test_sqlite_identity.py` | update |
| `tests/backend/test_sqlite_recovery.py` | update |
| `tests/backend/test_sqlite_history.py` | update |
| `tests/backend/test_sqlite_task_integrity.py` | create |
| `tests/backend/test_task_http.py` | create |
| `tests/backend/test_task_runtime.py` | create |
| `tests/backend/test_household_http.py` | update |
| `tests/backend/test_task_restoration.py` | create |
| `docs/evidence/task-execution-foundation.json` | create |
| `tooling/domus_tooling/backend_coverage.py` | create |
| `tests/python/test_backend_coverage.py` | create |
| `docs/household-api.md` | update |
| `docs/native-household-api.md` | update |
| `docs/sdd-validation.md` | update |
| `docs/development.md` | update |
| `specs/README.md` | reference |
| `specs/household-identity.md` | update |
| `specs/points-rewards.md` | update |
| `backend/src/domus/domain/identity.py` | update |
| `backend/src/domus/application/ports.py` | update |
| `backend/src/domus/infrastructure/sqlite_snapshots.py` | update |
| `backend/src/domus/infrastructure/sqlite_history.py` | update |
| `backend/src/domus/composition/household.py` | update |
| `backend/src/domus/composition/ingress.py` | update |
| `backend/src/domus/composition/server.py` | update |
| `backend/src/domus/entrypoints/household_http.py` | update |
| `backend/src/domus/entrypoints/http.py` | update |
| `backend/src/domus/entrypoints/native_http.py` | update |
| `docs/contracts/household-api.openapi.json` | update |
| `docs/contracts/native-household-api.openapi.json` | update |
| `tooling/domus_tooling/cli.py` | update |
| `tests/python/test_cli.py` | update |
| `.github/workflows/ci_check.yml` | update |
| `tests/python/test_ci_contract.py` | update |
| `tests/architecture/test_python_architecture.py` | update |
| `tests/backend/test_identity_policy.py` | update |
| `tests/backend/test_household_runtime.py` | update |
| `tests/backend/test_sqlite_transactions.py` | update |
| `tests/backend/test_sqlite_snapshots.py` | update |
| `tests/backend/test_sqlite_restoration.py` | update |
| `tests/backend/test_sqlite_history_integrity.py` | update |
| `tests/backend/test_owned_generations.py` | update |
| `tests/backend/test_restored_commands.py` | update |

Document title-only creation, claim, completion/approval defaults, existing proof/session/permissions, pending consumers, replay/restore/settlement/recovery, ports, migration, OpenAPI and coverage. Add no gateway/login. Synchronize examples with fixtures and actual API artifact conventions. Validate links/navigation, spec/catalog and unchanged pinned format/consistency/catalog checks plus `uv run domus-check docs`. Missing artifacts confer no evidence.

## 16. Acceptance

These are executable acceptance scenarios for future implementation; none is represented as run or passed.

1. Given a verified adult and a valid title-only create request with an idempotency key, when the command commits, then one definition, one available occurrence, one receipt, and one uniquely identified event exist atomically; replay returns the same facts. An empty title is invalid and produces none of those effects.
2. Given an available task offered to a restricted member’s profile and claim enabled, when that member claims at the current revision, then the server assigns the authenticated actor; concurrent claims yield one winner and required approval remains in force.
3. Given a completion with multiple actual performers, when saved, then assigned members, performer set, recording actor, performed time, policy snapshot, recorded time, and cycle ID remain distinct and queryable.
4. Given any restricted performer, when an adult approval is pending or rejected, then no Points award is reported; an authorized adult may approve under current authority and the cycle snapshot rules.
5. Given a completed occurrence, when authorized reopening names its current cycle, then that cycle closes, one compensating source event is retained, no physical stock return is fabricated, and completed dependents remain completed with a review condition.
6. Given valid material use without applicable authority, when completion commits, then work is saved with pending authorization and no movement; later explicit settlement rechecks current authority and stable intent identity.
7. Given insufficient stock or unavailable Inventory, when valid work is recorded, then no negative or synthetic movement appears; shortage is pending regularization and unavailable consumer is pending processing.
8. Given a foreign material line, forged actor/household, stale revision, revoked proof, changed idempotency payload, or old-cycle event, when submitted, then it is rejected/conflicted before unsafe effects and retained facts remain intact.
9. Given each HTTP route, when sent with extra fields, invalid bounds, missing proof/Origin/CSRF, or cross-installation IDs, then a bounded error is returned and no command is invoked; valid requests in both compositions use the same application service.
10. Given a restart, migration rollback, or restore, when task records and processed operation facts are inspected, then uniqueness, history, and duplicate suppression are preserved or restore fails closed.
11. Given the five primary UX states, when rendered in supported locale and narrow/light/dark contexts, then status, completed facts, next action, impact, links, and textual equivalents remain understandable and sanitized.
12. Given the complete authored backend source inventory, when required CI runs on the PR head, then every module has 100% executed statement and branch coverage, dependency/cycle checks pass, all required existing CI groups pass, and full-context Bugbot has no unresolved finding. This validates implementation only after it exists.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| TEF-01 | task-execution-foundation-C01, task-execution-foundation-C02, task-execution-foundation-C15, task-execution-foundation-C16 |
| TEF-02 | task-execution-foundation-C01, task-execution-foundation-C03 |
| TEF-03 | task-execution-foundation-C04, task-execution-foundation-C05, task-execution-foundation-C06, task-execution-foundation-C07, task-execution-foundation-C18, task-execution-foundation-C19 |
| TEF-04 | task-execution-foundation-C08, task-execution-foundation-C09, task-execution-foundation-C17 |
| TEF-05 | task-execution-foundation-C18, task-execution-foundation-C20, task-execution-foundation-C42 |
| TEF-06 | task-execution-foundation-C10, task-execution-foundation-C11, task-execution-foundation-C21, task-execution-foundation-C22, task-execution-foundation-C23 |
| TEF-07 | task-execution-foundation-C14, task-execution-foundation-C23, task-execution-foundation-C24, task-execution-foundation-C25 |
| TEF-08 | task-execution-foundation-C12, task-execution-foundation-C13, task-execution-foundation-C26, task-execution-foundation-C27, task-execution-foundation-C28, task-execution-foundation-C29, task-execution-foundation-C33, task-execution-foundation-C34 |
| TEF-09 | task-execution-foundation-C30, task-execution-foundation-C34, task-execution-foundation-C35 |
| TEF-10 | task-execution-foundation-C42 |
| TEF-11 | task-execution-foundation-C15, task-execution-foundation-C16, task-execution-foundation-C31, task-execution-foundation-C32, task-execution-foundation-C36 |
| TEF-12 | task-execution-foundation-C37, task-execution-foundation-C38, task-execution-foundation-C39 |
| TEF-13 | task-execution-foundation-C42 |
| TEF-14 | task-execution-foundation-C40, task-execution-foundation-C41 |

## 18. Implementation sequence

1. Publish the validated companion on the linked managed branch; preserve all 49 owning cases.
2. Finalize route/OpenAPI, schema, graph, inventory, policy and documentation contracts before code.
3. Implement pure Domain policies and exhaustive tests.
4. Implement Application commands, queries, current authority, receipts, atomic outbox and races.
5. Implement SQLite migration/restart/rollback/restore and semantic Inventory/event adapters with explicit pending states.
6. Wire both Python compositions and bounded DTOs; document users, setup, operations and contribution.
7. Require whole-backend/per-module coverage, real SQLite/loopback, all CI and full-context Bugbot. Later actual HA and Inventory/Points acceptance remain mandatory. Companion publication and exact branch validation precede implementation.

## 19. Definition of Done

- [ ] Every normative requirement has acceptance and reciprocal case traceability.
- [x] This new companion was validated/published before implementation on its exact managed branch; `specs/household-tasks.md` remains intact with its 49 cases.
- [ ] Architecture boundaries, dependency graph, cycles, OpenAPI, schema, and module inventory are executable checks.
- [ ] Numeric budget and per-module plus whole-backend 100% statement/branch coverage pass without exclusions or denominator reduction.
- [ ] Configuration limits, defaults, authority, snapshots, and migration agree with code and fixtures.
- [ ] All five primary UX states, sanitization, accessibility, localization, responsive behavior, and noise budgets pass review.
- [ ] User, setup, operator, contributor, migration, and troubleshooting documentation is complete and discoverable.
- [ ] Failure, partial success, retry, idempotency, concurrency, revocation, restore, security, and cleanup scenarios pass.
- [ ] Required CI jobs pass at current head and full-context Bugbot has no unresolved findings; immutable Copilot checks remain intact.
- [ ] Real SQLite/loopback and port-fake evidence are distinguished; owner HA adoption and real consumer delivery are required before integrated release claims.
- [ ] `specs/catalog.json` evidence and `specs/CATALOG.md` are current and the unchanged pinned SDK format/consistency/catalog validators and `uv run domus-check docs` passes.
- [ ] No readiness-blocking decision remains unresolved; Draft readiness blockers are not waived by this document.

## 20. References and decisions

- Primary sources: verified immutable-base catalog and owning specification; `docs/architecture.md`; `docs/decisions.md`; `docs/roadmap.md`; `docs/m1-acceptance-audit.md`.
- Related spec: `specs/household-tasks.md`; this companion adds a distinct case namespace and does not replace it.
- Issue: https://github.com/vypdev/domus/issues/13.
- Decisions: preserve separate definition/occurrence/cycle identities; title-only atomic create; eligible restricted-member self-claim default confirmed 2026-10-31; current proof and authorization; adult approval for any restricted performer; retain actual versus recorded/approved/posted times; explicit material settlement; consumer-owned ledgers; full first-party backend line and branch coverage.
- Rejected alternatives: one completed flag; implicit reassignment; omission-based verification bypass; synthetic ledger events; second inventory ledger; gateway/MCP or permission bypass; replacing the existing owner specification; treating source paths or fixtures as runtime acceptance.
- Follow-up outside scope: recurrence execution, full task UI, real Inventory and Points domains/consumers, all-domain acceptance, both deployment target acceptance, isolated Stable/Edge, and actual HA entity/service acceptance before first usable release.
