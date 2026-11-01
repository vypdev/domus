# Durable recurrence execution and calendar queries

- Status: Draft
- Date: 2026-11-01
- Catalog capability ID: recurrence-calendar
- Last verified: not applicable; prospective implementation
- Owners: Domus maintainer and product owner
- Scope: Durable task recurrence, bounded maintenance and calendar application/API facts
- Related issues/PRs: https://github.com/vypdev/domus/issues/17
- Required review gates: product UX, architecture, tests, documentation, security/operations
- Open decisions blocking readiness: none; implementation and acceptance remain unproven

This companion preserves the unchanged [owning recurrence contract](recurrence-calendar.md), its eight requirements and all 37 original cases. The first usable release still includes all domains, the complete calendar interface, HA surface, both deployments and isolated Stable/Edge. This internal backend increment does not establish that acceptance. Engineering bounds below are reviewed proposals, not separately confirmed owner choices.

## 1. Executive summary

Create actual, uniquely identified task occurrences from fixed or completion-relative schedules. Keep the confirmed local-calendar anchor, first-valid gap resolution, one configured fold appearance and actual-work successor date. A bounded local runner retains durable progress; authorized calendar queries distinguish planned work, deadlines and actual performance. Existing work and receipts survive retries, edits and restoration without silent duplication.

```text
Authorized schedule -> reviewed rule and plan -> bounded durable materialization -> actual task facts -> authorized calendar read
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Tasks have a durable lifecycle but no recurrence service. A family cannot yet obtain repeatable scheduled work or a truthful date-only/instant calendar projection. Library defaults alone do not implement the confirmed gap and relative-time policies.

### 2.2 Current behavior

1. Immutable base 63d1159f83f51ae0cd3c41f32341d9e9e36bb6da, tree f1e3aa8f9e8408076ca6c9740ace5391f8ac8c2b, contains the real task model, current authority, HTTP boundaries and SQLite schema 7.
2. Ordinary task creation creates one initial occurrence. A schedule must not accidentally create a second copy of that first obligation.
3. The typed TaskEventSource supplies original completion, verification and reopening facts. It is not a recurrence consumer or delivery acknowledgement.
4. Occurrences currently have an optional instant deadline. Separate planned start, date-only deadline, category and task-type contracts are incomplete. No runner or recurrence persistence is present.

### 2.3 Evidence

Existing code: `backend/src/domus/domain/tasks.py`, `backend/src/domus/domain/task_values.py`, `backend/src/domus/application/task_events.py`, `backend/src/domus/application/task_commands.py`, `backend/src/domus/application/task_queries.py`, `backend/src/domus/infrastructure/sqlite.py`, `backend/src/domus/composition/tasks.py` and `backend/src/domus/entrypoints/task_http.py`.

The public immutable archive was checked against all 430 tracked Git blobs. Exploratory Python 3.14.6, dateutil 4.0.0 and pinned tzdata 2026.6/IANA 2026f controls show full-gap shifting, nonexistent aware candidates and permissive raw-rule parsing. These are adapter observations, not product acceptance. Exact production dependency hashes must be locked and verified before use.

### 2.4 Retrospective classification

Not applicable to this prospective companion. The numbered baseline above identifies source facts; the following requirements describe work still to implement. The historical owner's initial empty-repository baseline is retained rather than rewritten as current evidence.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
|---|---|---|---|
| Authorized task manager | Configure and review work | Existing verified native or standalone API | Rule, preview, conflict and receipt |
| Active reader | Understand household dates | Protected calendar query | Actual authorized entries and freshness |
| Local maintenance capability | Materialize configured work | Composition-bound runner | Bounded status, cursor and failure |
| Operator | Upgrade or recover | Existing owned-storage procedure | Compatible image/data and historical proof |

A nominal slot is the original local date/time under a rule revision. Its resolved instant may differ. A source cycle is actual performed work, not an assignee or verification timestamp. A plan is a bounded reviewed proposal, not permission. A processed historical slot may have no current task effect after restoration. Maintenance is a narrow technical capability, never a human HA identity or performer.

## 4. Goals

| Requirement | Behavior |
|---|---|
| RCE-01 | Validate a closed schedule/classification contract and preserve title-only creation without duplicate initial work. |
| RCE-02 | Resolve nominal slots deterministically using the declared zone policy, retaining date-only values and nominal identity. |
| RCE-03 | Materialize bounded unique work with atomic progress, source checks and owned production-runner lifecycle. |
| RCE-04 | Consume actual task lifecycle facts once per source/cycle and retain successor closure/review and restore semantics. |
| RCE-05 | Preview and revision-check edits, exceptions, pause/resume and future replacements while preserving started work/history. |
| RCE-06 | Return bounded authorized calendar facts with actual classification, consistent predicates and explicit incomplete state. |
| RCE-07 | Preserve current human authority, narrow technical scope, installation/channel ownership and compatible migration/recovery. |
| RCE-08 | Enforce Clean Architecture, meaningful 100% first-party coverage and truthful documentation/deployment evidence. |

Full calendar UI, HA calendar export and real Points/Inventory delivery remain required by their owners and launch gate; this companion does not claim to implement those surfaces. Do not change Copilot, gateway, credentials or remote branch lifecycle. Current authorization, attribution, original receipts, fixed invariants and physical stock/ledger ownership cannot be weakened by configuration.

## 5. Current versus proposed product journey

| Stage | Current | Proposed | Effect |
|---|---|---|---|
| Define | Manual initial task only | Explicit validated schedule or reviewed attachment | No accidental duplicate first work |
| Generate | No recurrence consumer | Atomic bounded runner | Stable slots survive concurrent restart |
| Observe | Task facts only | Scheduled, due and actual calendar entries | Incomplete processing is visible |
| Correct | No rule plan | Explicit preview and current revision | Existing work/history are preserved |

```mermaid
flowchart LR
 Configure[Review schedule] --> Persist[Save rule and receipt]
 Persist --> Materialize[Bounded durable run]
 Materialize --> Calendar[Read actual calendar facts]
```

Text equivalent: a deliberate configuration saves its original result; bounded maintenance creates actual task work; protected queries expose that work with its processing state.

## 6. Functional behavior and state model

### 6.1 Normal path and ownership

New scheduled-task creation is atomic across its task definition, schedule, any first materialized occurrence, receipt, audit and outbox. Reuse task validation/current authority and material ownership. Keep the existing title-only path unchanged. An explicit attachment to existing work reviews the existing first occurrence: retain it as manual work, or explicitly adopt a compatible unstarted occurrence at its exact revision. Never silently merge histories, delete the initial task or generate two first obligations. The preview identifies which choice will apply.

Fixed rules preserve their calendar anchor after late work. Generate naive nominal calendar candidates, then apply the explicit Domus zone resolver. COUNT counts nominal valid-date rule slots before explicit exclusions; gap-adjusted slots are retained. Invalid dates such as February 31 follow omission. Explicit additions and exclusions retain their own identities and provenance. DTSTART must match the supported rule pattern; otherwise return the field error and first permitted candidate without silently rewriting the submitted command. Set week-start and every provider default explicitly.

Completion-relative rules have an explicit initial due date/instant before their first completion, or a reviewed reference to an existing eligible current completion. Thereafter add the configured number of local calendar days to actual performed_at in the snapshotted zone, retaining its local time and millisecond precision for instant deadlines. Do not substitute verified_at or a fixed UTC duration. The default at_completion exposes one successor while approval/points remain pending; at_verification waits for accepted verification but retains the performed-at-derived date, including overdue dates.

Read original current TaskEventSource facts, including their original state and position. Persist inbox, per-cycle closure and successor identity with the task changes. Duplicate or out-of-order delivery cannot reopen a closed cycle or grant an award. Rejection/reopening invalidates an unstarted derived successor with retained reason/history. Started or completed downstream work remains with a review condition. A technical consumer never invents an actor, performer, approval, stock movement or point award.

### 6.2 Time policy

For an ordinary nonexistent wall time, advance to the first valid local instant at or after the nominal slot; Madrid 02:30 in a 02:00-03:00 gap resolves to 03:00. A half-hour gap uses its actual first boundary. A wholly missing local date advances to the first valid subsequent instant and retains its nominal date. This whole-date extension is a maintainer engineering decision, not a separately confirmed owner answer. Distinct nominal slots remain distinct if their resolved instants coincide; flag that collision for review instead of merging or losing obligations.

Check existence before ambiguity: a library's ambiguous flag alone may be true for a nonexistent candidate. A fold selects exactly one configured appearance, first by default, with the household's explicit second option. Store zone, nominal value, resolved offset/instant, resolution reason, rule/time-policy revision and timezone-data identity. Never deduplicate by resolved UTC instant alone. This is Domus policy layered over nominal generation, not full raw RFC 5545 conformance.

Use the pinned timezone source through an isolated adapter; do not reset process-global TZPATH or silently use a different machine database. Existing resolved instants remain facts. A future timezone-data change requires explicit compatibility review and a preview for affected unstarted future work; it cannot reinterpret active/completed records silently. Unknown zones and unavailable/corrupt source data have distinct bounded failure states. Date-only deadlines stay dates and have no invented duration or UTC midnight.

### 6.3 Durable states and alternatives

| State | Entered when | Meaning | Next states | Recovery |
|---|---|---|---|---|
| Active | Authorized rule committed | Future work can be generated | Paused, retired, revised | Bounded maintenance |
| Paused | Explicit pause | Existing work remains | Active, retired | Reviewed resume |
| Retired | Explicit retirement | No new slots | Historical only | New deliberate rule |
| Prepared plan | Current bounded preview | No business change yet | Applied, stale, expired | Review/refresh |
| Processing incomplete | Backlog or bounded continuation | Calendar may be incomplete | Current, unavailable | Resume persisted cursor |
| Review required | Retained started successor or collision | Existing work is preserved | Reviewed resolution | Current manager |
| Historical absent effect | Restored processed operation | It was processed, effect absent | Explicit new reviewed work | Never automatic recreation |

All writes use original key/payload and optimistic revisions. A changed payload with the same key conflicts. A lost response recovers its original receipt before stale-revision rejection. Uncertain work is not replaced by a fresh key or automatic retry. Rule/occurrence/source snapshots are rechecked inside the commit. Pause stops new materialization, not existing assigned work. Missed work remains visible by default; reviewed skipping retains reason/identity and awards no completion points.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| Schedule kind | Enum | Explicit selection | Fixed or completion-relative | Definition/rule revision |
| Fixed frequency | Enum | Explicit selection | DAILY, WEEKLY, MONTHLY, YEARLY | Rule |
| Interval | Integer | 1 | 1..366 for fixed; 1..36600 local days for relative | Rule |
| Week start | Enum | MO | MO, TU, WE, TH, FR, SA, SU | Fixed rule, separate from display preference |
| BYDAY | Typed unique list | None | At most 35; plain weekdays, ordinal -5..-1 or 1..5 only in permitted monthly/yearly combinations | Rule |
| BYMONTH | Unique integer list | None | 1..12, at most 12 | Rule |
| BYMONTHDAY | Unique integer list | None | -31..-1 or 1..31, at most 62; reject unsupported weekly combination | Rule |
| BYSETPOS | Unique integer list | None | -366..-1 or 1..366, at most 32; requires a supported BY selector | Rule |
| End condition | Tagged value | No end | COUNT 1..100000 or UNTIL, mutually exclusive | Rule |
| Dates/time | Strict Gregorian value | Explicit | Years 1970..9999, fixed minute precision; range/UTC conversion overflow rejected | Rule/occurrence |
| Time zone | Validated IANA key | Explicit household-zone snapshot | 1..128 characters, actual pinned source | Rule/policy |
| Repeated time | Enum | first_instant | first_instant or second_instant | Household policy snapshot |
| Successor visibility | Enum | at_completion | at_completion or at_verification | Per task |
| Missed work | Enum | keep_visible | keep_visible or skip_after_review | Per task |
| Exceptions/additions | Typed unique list | None | At most 128 of each; matching date/time kind and bounded reason | Rule revision |
| Reschedule/skip reason | Text | Explicit | Nonblank 1..1000 characters; inert UTF-8, no forbidden controls | Exception/audit |
| Horizon | Integer days | 60 | 7..366; future horizon, never implicit deletion of past backlog | Household/runner |
| Run limits | Integers | 1000 total slots | At most 1000 per definition and globally per run; at most 50 definitions considered | Maintenance state |
| Preview | Bounded plan | Explicit range | At most 366 days, 1000 affected occurrences, expires after 300 seconds | Persisted plan/revisions |
| Query range/page | Half-open date range/integer | 31 days, 25 rows | Range 1..366 days; page 1..100; context-bound cursor expires after 300 seconds | Protected query |
| Category | Optional reference | No classification for legacy work | Exact active household category; category label 1..80 inert characters | Task-owned classification |
| Timing type | Enum | one_time for new ordinary manual work | one_time, fixed_calendar, completion_relative; derive actual configured timing | Task-owned classification |

Reject duplicate keys/values, unsupported RRULE parts, COUNT plus UNTIL, unknown versions, invalid UTF-8, unbounded lists and contradictory combinations before provider invocation. Subdaily frequencies, BYSECOND, BYMINUTE, BYHOUR, BYWEEKNO, BYYEARDAY and extensions are unsupported in this first rule contract. Do not partially interpret them. Seasonal scheduling uses supported yearly/month/weekday forms. Original advanced condition/event task types remain part of their owning later automation/task contracts, not fabricated as active schedules here.

Category is not a tag alias. Add a genuine task-owned category/classification contract with foreign/inactive-reference checks. Legacy unclassified work remains explicitly unclassified, not an invented category. Only title remains mandatory for ordinary creation. Schedule kind never turns a technical principal into a household member.

## 8. Clean Architecture

Domain owns immutable validated schedule/time/plan values and transition rules. Application owns current-authorized configuration, materialization, source consumption, preview/apply and bounded queries through semantic ports. Infrastructure adapts pinned nominal expansion/time resolution, SQLite and transport errors. Composition alone binds installation/channel, production runner and existing native/standalone session adapters. Presentation later consumes the same facts and emits deliberate intents.

Reuse the existing task, identity, atomic-command, owned-storage and lifecycle-source guarantees. Extract shared application creation/transition behavior where necessary rather than bypassing its validation or copying an alternative permission system. Inner layers import no FastAPI, SQLite, provider/library DTO, browser framework or concrete adapter. Port contracts cover missing, denied, unavailable, stale and corrupt results without fake empty success.

The runner is an explicit local technical capability bound to one installation/channel/household and configured active rules. It may create only the generated task work and owned progress/events authorized by those rules. It cannot perform human work, edit member permissions, approve tasks or touch Points/Inventory ledgers. Ordinary task scheduling uses existing task-create/manage grants; administrator-only policy overrides retain task-configuration authority. Source/rule changes are transactionally checked before maintenance writes.

## 9. UI/UX and content contract

This increment exposes truthful typed API/status facts for later EN/ES views. It does not count fixture rendering or backend JSON as actual calendar UI acceptance.

| State | Required meaning |
|---|---|
| Pending | The bounded run has more work; this range may be incomplete. |
| Action required | Review changed future slots or the resolved local-time adjustment. |
| Blocked | Unsupported rule or stale plan; existing work is retained. |
| Partial | The task is saved; a downstream projection is still pending. |
| Complete | This batch committed; its continuation/freshness is explicit. |

Distinguish planned start, deadline, actual performed time, approval and processing time. Do not imply earned points or a sent notification without the owning consumer. Fixed identifiers, safe codes and correlations are progressively disclosed; provider messages never become presentation HTML. Later month/week/day/agenda views, keyboard/mobile/dark/reduced-motion and localization remain mandatory under the owner.

## 10. Failure, recovery, and cleanup

Failure before commit leaves tasks, cursor, inbox, receipt and outbox unchanged. A crash after commit resumes the persisted continuation and uniqueness proof. Bound I/O, batch work and retries/backoff through injected clocks; a failed provider cannot spin indefinitely or fabricate no work. Backlog is visible, with fair continuation across definitions.

Apply only a current reviewed plan: preserve started/completed/performed-pending-approval work and explicit exceptions; a concurrent start/source/policy change invalidates the plan. Removed eligible future slots are cancelled with replacement reason/link, never deleted. Retain compatible assignment/annotations and expose conflicts. Stop scheduling new steps on shutdown; an in-progress atomic step completes or rolls back, and owned resources are joined/disposed before storage closes.

Restoration selects historical business state while retaining later processed proofs. A restored older cursor, missing fixed slot or absent relative successor cannot trigger automatic recreation of its already-processed effect. Display historical absence and require a deliberate reviewed new intent if work should be created again. Reopening does not imply stock return or award compensation. Remove owned temporary artifacts after retaining necessary evidence and rollback inputs.

## 11. Security, permissions, and privacy

Native and standalone reuse their actual current human proof, Origin, session CSRF, expected context, strict bounded JSON and original idempotency. No body selects actor, installation, channel or technical authority. Current membership/policy and original-action authority apply to receipt recovery as well as new commands. Suspended/revoked users and stale dialogs cannot disclose old protected results.

Protected reads use current local authority and only the existing original-deadline outage lease; grace never permits changes. Filter IDs must belong to the same household. Cursors bind range, filters, page size, installation/channel and principal, and cannot grant access. Missing proof differs from actual availability failure. Never expose raw HA payloads, technical tokens, private preferences or owner browser artifacts. External calendar transmission remains disabled.

## 12. Observability and operational UX

Return safe rule/plan/run identifiers, revision, processed count, continuation/backlog, last committed position, projection freshness, bounded error category and retained review conditions. Counts share the actual entry predicate; distinguish event rows from distinct occurrences. A planned/deadline entry uses assignment filtering; actual history uses real performers. Do not equate a ledger-unavailable result with zero earned points. One durable activity/outbox effect per committed transition; no acknowledgement for unexecuted downstream consumers.

## 13. Compatibility, migration, rollout, and rollback

Issue17 owns schema 8 first. Issue16 follows on the Action-selected recurrence merge with schema 9; its earlier schema-8 proposal is superseded. Preserve supported historical schemas 1..7 and immutable fixtures. Add verified typed tables/metadata and migration under the existing ownership/generation transaction boundary; original receipts, audit payload hashes and source snapshots remain authoritative. Unknown future, unrelated, corrupt or mismatched installation/channel inputs are rejected before business writes.

Normal transactions require the current schema. Upgrade an owned supported source atomically; failure rolls back both additions and version advancement. Original snapshot/source bytes remain untouched during prepared restore activation. Old schema-7 images, including Edge.5, refuse schema 8 rather than downgrade. Retain exact pre-upgrade application/database/generation pairs through acceptance and until explicit operator cleanup; do not introduce an automatic retention schedule. Rollback is the compatible complete pair, not a user_version edit. Both actual image architectures and both persistent runtime compositions need new evidence before an updated package claim. No owner HA upgrade is authorized merely by this specification.

## 14. Testing strategy and numeric budget

Minimum: 52 distinct boundary cases below. Preserve all 37 original owner cases. A test that also discharges an owner scenario is not two independent executed journeys. All supported first-party metrics must be 100% globally and per module from the first source change; cases and coverage are separate evidence. Start with meaningful failing behavior tests. Use deterministic source facts, clocks, IDs, independent SQLite connections, crash injection and real composed HTTP/image tests. Current UI/HA/consumer acceptance remains unclaimed.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Configuration | 8 | Observable scenarios in the case inventory. |
| Time adapter | 7 | Observable scenarios in the case inventory. |
| Durable work | 8 | Observable scenarios in the case inventory. |
| Lifecycle | 7 | Observable scenarios in the case inventory. |
| Plans | 6 | Observable scenarios in the case inventory. |
| Calendar | 6 | Observable scenarios in the case inventory. |
| Security recovery | 6 | Observable scenarios in the case inventory. |
| Composition quality | 4 | Observable scenarios in the case inventory. |
| Total | 52 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| recurrence-execution-C01 | Configuration | RCE-01 | Supported daily, weekly, monthly and seasonal yearly rules produce their explicit bounded nominal pattern. |
| recurrence-execution-C02 | Configuration | RCE-01 | Duplicate FREQ and COUNT plus UNTIL are rejected before the permissive provider can interpret them. |
| recurrence-execution-C03 | Configuration | RCE-01 | COUNT, terminal UNTIL and explicit exclusions preserve the documented nominal counting/end semantics. |
| recurrence-execution-C04 | Configuration | RCE-01 | Out-of-bound intervals/lists and unsupported subdaily or extension parts produce a field error with no write. |
| recurrence-execution-C05 | Configuration | RCE-01, RCE-06 | Foreign/inactive category references fail; legacy unclassified work is not converted from tags. |
| recurrence-execution-C06 | Configuration | RCE-01, RCE-03 | Atomic scheduled creation retains the existing ordinary path without an unintended extra first occurrence. |
| recurrence-execution-C07 | Configuration | RCE-01, RCE-05 | Reviewed attachment retains existing manual work or adopts only the explicitly selected compatible unstarted revision. |
| recurrence-execution-C08 | Configuration | RCE-01, RCE-02 | Explicit DTSTART and week-start make results independent of wall-clock and process calendar defaults. |
| recurrence-execution-C09 | Time adapter | RCE-02 | The Madrid gap resolves a nominal 02:30 once to 03:00 while retaining its key and adjustment. |
| recurrence-execution-C10 | Time adapter | RCE-02 | A Lord Howe half-hour gap resolves to its first valid boundary rather than adding 30 minutes. |
| recurrence-execution-C11 | Time adapter | RCE-02 | First/second fold policies each select one valid appearance and preserve one nominal identity. |
| recurrence-execution-C12 | Time adapter | RCE-02 | A wholly missing Apia date resolves to the next first valid instant with nominal date and collision attention retained. |
| recurrence-execution-C13 | Time adapter | RCE-02, RCE-08 | Pinned timezone bytes produce the same resolution with a different/unavailable machine timezone database. |
| recurrence-execution-C14 | Time adapter | RCE-02 | Unknown zone and unavailable/corrupt timezone source remain distinct bounded failures without silent fallback. |
| recurrence-execution-C15 | Time adapter | RCE-02 | Date, UTC conversion and millisecond boundary overflow fail without wrapping or inventing a slot. |
| recurrence-execution-C16 | Durable work | RCE-03 | Per-rule/global limits, horizon and fair persisted continuation bound a large multi-definition backlog. |
| recurrence-execution-C17 | Durable work | RCE-03 | Independent concurrent database writers commit exactly one task for each nominal rule slot. |
| recurrence-execution-C18 | Durable work | RCE-03 | Failure after task insertion rolls back task, cursor, inbox, receipt and outbox together. |
| recurrence-execution-C19 | Durable work | RCE-03 | Crash after commit resumes from persisted proof without another task or activity event. |
| recurrence-execution-C20 | Durable work | RCE-03, RCE-05 | Rule/source changes after planning invalidate the transaction instead of applying stale effects. |
| recurrence-execution-C21 | Durable work | RCE-03, RCE-05 | Pausing stops future materialization and retains already-assigned work and its history. |
| recurrence-execution-C22 | Durable work | RCE-03, RCE-08 | Shutdown finishes or rolls back the atomic step, starts no next step and disposes owned resources before storage. |
| recurrence-execution-C23 | Durable work | RCE-03, RCE-06 | An incomplete backfill returns explicit backlog/freshness rather than a complete empty calendar. |
| recurrence-execution-C24 | Lifecycle | RCE-04 | One current pending completion creates the default successor once without claiming approval or points. |
| recurrence-execution-C25 | Lifecycle | RCE-04 | Delayed verification creates one overdue successor at the performed-at-derived date under at_verification. |
| recurrence-execution-C26 | Lifecycle | RCE-04 | Rejection/reopening closes the original cycle and cancels only its unstarted derived successor with retained history. |
| recurrence-execution-C27 | Lifecycle | RCE-04 | A started/completed successor survives source reopening with review attention and no invented compensation. |
| recurrence-execution-C28 | Lifecycle | RCE-04 | Reordered duplicate source delivery and tied timestamps use original positions and durable cycle closure. |
| recurrence-execution-C29 | Lifecycle | RCE-02, RCE-04 | Relative local days preserve actual-work wall time across 23-hour and 25-hour days independently of approval. |
| recurrence-execution-C30 | Lifecycle | RCE-04, RCE-07 | Restored-away approval/closure source cannot recreate a current successor from historical absent effects. |
| recurrence-execution-C31 | Plans | RCE-05 | Applying a reviewed edit replaces only eligible unstarted future work and retains performed/started/history records. |
| recurrence-execution-C32 | Plans | RCE-05, RCE-07 | A concurrent start invalidates the exact preview and returns conflict without overwriting the occurrence. |
| recurrence-execution-C33 | Plans | RCE-05 | Rebuilding retains explicit exclusions, skips and manual reschedules with their provenance. |
| recurrence-execution-C34 | Plans | RCE-03, RCE-05 | A lost apply response replays the original rule and linked replacement IDs without duplicate effects. |
| recurrence-execution-C35 | Plans | RCE-02, RCE-05 | Distinct nominal slots resolving to the same instant remain traceable and require visible review instead of silent merge. |
| recurrence-execution-C36 | Plans | RCE-02, RCE-05 | A fold/timezone-data policy preview preserves active/completed resolved instants and rejects stale application. |
| recurrence-execution-C37 | Calendar | RCE-02, RCE-06 | A date-only deadline remains the same date when the display zone changes; no start/duration is invented. |
| recurrence-execution-C38 | Calendar | RCE-06 | Excessive ranges/pages, duplicate/unknown parameters and altered cursor bindings fail with bounded errors. |
| recurrence-execution-C39 | Calendar | RCE-06 | Combined actual category/type/status/priority predicates match entry counts and distinct-occurrence counts. |
| recurrence-execution-C40 | Calendar | RCE-06 | Planned assignment and actual performer filters yield their separate truthful scheduled/history facts. |
| recurrence-execution-C41 | Calendar | RCE-06 | Stable entry identity includes kind and cycle so retry/reload does not confuse a deadline with completion history. |
| recurrence-execution-C42 | Calendar | RCE-06, RCE-07 | Original-deadline outage reads retain current local masking and never permit a scheduling write. |
| recurrence-execution-C43 | Security recovery | RCE-07 | Current HA/local revocation blocks stale configuration and protected original-result recovery without side effects. |
| recurrence-execution-C44 | Security recovery | RCE-03, RCE-07 | Foreign household/installation/channel and submitted technical actor selectors cannot reach maintenance authority. |
| recurrence-execution-C45 | Security recovery | RCE-07 | Genuine schema-7 fixtures upgrade atomically while original receipt/source/history facts remain authoritative. |
| recurrence-execution-C46 | Security recovery | RCE-07 | Unknown/future/corrupt schemas and injected DDL failure preserve owned source/version and reject unsafe writes. |
| recurrence-execution-C47 | Security recovery | RCE-03, RCE-07 | A restored older fixed-slot cursor honors later historical processed proof rather than regenerating its absent task. |
| recurrence-execution-C48 | Security recovery | RCE-07, RCE-08 | An old actual image refuses the new schema and the compatible complete application/data pair supports rollback. |
| recurrence-execution-C49 | Composition quality | RCE-03, RCE-08 | Both persistent native/standalone runtimes wire the real runner/queries; preview does not claim functioning recurrence. |
| recurrence-execution-C50 | Composition quality | RCE-03, RCE-08 | A provider/lock failure has bounded retry/backoff and visible state without spinning or certifying downstream delivery. |
| recurrence-execution-C51 | Composition quality | RCE-02, RCE-08 | Actual amd64/aarch64 package tests execute the pinned recurrence/time dependencies and required migration path. |
| recurrence-execution-C52 | Composition quality | RCE-08 | Current-source architecture/privacy negatives and per-module/global coverage fail closed for a real forbidden import or missing branch. |

## 15. Documentation and discoverability

| Path | Change |
|---|---|
| specs/recurrence-execution-foundation.md | create |
| specs/recurrence-calendar.md | reference |
| specs/task-execution-foundation.md | reference |
| specs/catalog.json | update |
| specs/CATALOG.md | update |
| docs/development.md | update |
| docs/architecture.md | update |
| docs/acceptance-plan.md | update |
| docs/tasks/execution.md | update |
| docs/tasks/migration.md | update |
| docs/contracts/household-api.openapi.json | update |
| docs/contracts/native-household-api.openapi.json | update |

Implementation will declare actual new source/test paths before committing those files; this prospective document does not claim nonexistent artifacts as current. User/operator guides must explain original-command recovery, nominal/resolved time, backlog, pending downstream consumers, schema compatibility and actual acceptance limits. Preserve dated evidence as history and add exact new revision/commands/results instead of relabeling old evidence.

## 16. Acceptance

These are planned executable acceptance scenarios, not executed tests. Run each against the current implementation and preserve its observable result and evidence before claiming acceptance.

1. Given a task definition and an authorized manager saving a daily schedule, when its first bounded run commits, then exactly one initial obligation exists with a stable nominal key and a replayed lost response returns the same receipt.
2. Given a nominal 02:30 slot inside a 02:00-03:00 gap, when the resolver materializes it, then the occurrence resolves to 03:00 and exposes its nominal value, zone, offset, policy revision and adjustment.
3. Given a slot on a wholly missing local date, when it is resolved, then the first subsequent valid instant is retained alongside the original nominal date/key, with visible adjustment and collision review where needed.
4. Given a completion-relative task crossing a 23-hour local day, when actual work is performed and verification is delayed, then its successor uses performed_at plus local calendar days, never verified_at or a fixed 24-hour duration.
5. Given two concurrent runner instances and a crash after a committed batch, when both resume, then each nominal slot has one task and durable cursor/inbox/receipt/outbox state with visible remaining backlog.
6. Given a source reopening after an unstarted successor was derived, when current source state is reread, then that successor is invalidated with history; if it has started, it is retained with review attention and no fabricated compensation.
7. Given a rule edit preview whose occurrence starts before apply, when the manager submits the original plan revision, then apply returns a conflict and preserves the started occurrence and exact prior receipt.
8. Given a protected calendar query with date-only deadline, category, priority and status predicates, when the range is paged, then each row preserves the date-only value and matching counts, while actual performer history remains distinct from planned assignment.
9. Given a revoked human session, forged technical actor selector, foreign household cursor or expired context, when configuration or original-result recovery is attempted, then authorization fails before business writes and leaks no protected receipt.
10. Given schema 7 owned data, when schema 8 upgrade succeeds, then receipts and source history remain authoritative; if migration fails, the transaction leaves the source/version intact, and an old image refuses the new schema.
11. Given unavailable/corrupt timezone source or provider lock failure, when bounded maintenance runs, then it reports a safe unavailable state, does not silently fall back or spin, and can resume through explicit bounded retry.
12. Given both persistent native and standalone compositions, when the actual runner and query use cases are started and shut down, then owned lifecycle resources are joined before storage closes and unsupported UI/HA/release claims remain unmade.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| RCE-01 | recurrence-execution-C01, recurrence-execution-C02, recurrence-execution-C03, recurrence-execution-C04, recurrence-execution-C05, recurrence-execution-C06, recurrence-execution-C07, recurrence-execution-C08 |
| RCE-02 | recurrence-execution-C08, recurrence-execution-C09, recurrence-execution-C10, recurrence-execution-C11, recurrence-execution-C12, recurrence-execution-C13, recurrence-execution-C14, recurrence-execution-C15, recurrence-execution-C29, recurrence-execution-C35, recurrence-execution-C36, recurrence-execution-C37, recurrence-execution-C51 |
| RCE-03 | recurrence-execution-C06, recurrence-execution-C16, recurrence-execution-C17, recurrence-execution-C18, recurrence-execution-C19, recurrence-execution-C20, recurrence-execution-C21, recurrence-execution-C22, recurrence-execution-C23, recurrence-execution-C34, recurrence-execution-C44, recurrence-execution-C47, recurrence-execution-C49, recurrence-execution-C50 |
| RCE-04 | recurrence-execution-C24, recurrence-execution-C25, recurrence-execution-C26, recurrence-execution-C27, recurrence-execution-C28, recurrence-execution-C29, recurrence-execution-C30 |
| RCE-05 | recurrence-execution-C07, recurrence-execution-C20, recurrence-execution-C21, recurrence-execution-C31, recurrence-execution-C32, recurrence-execution-C33, recurrence-execution-C34, recurrence-execution-C35, recurrence-execution-C36 |
| RCE-06 | recurrence-execution-C05, recurrence-execution-C23, recurrence-execution-C37, recurrence-execution-C38, recurrence-execution-C39, recurrence-execution-C40, recurrence-execution-C41, recurrence-execution-C42 |
| RCE-07 | recurrence-execution-C30, recurrence-execution-C32, recurrence-execution-C42, recurrence-execution-C43, recurrence-execution-C44, recurrence-execution-C45, recurrence-execution-C46, recurrence-execution-C47, recurrence-execution-C48 |
| RCE-08 | recurrence-execution-C13, recurrence-execution-C22, recurrence-execution-C48, recurrence-execution-C49, recurrence-execution-C50, recurrence-execution-C51, recurrence-execution-C52 |

## 18. Implementation sequence

1. Define typed schedule, classification, time-resolution and semantic-port contracts; confirm executable boundary constraints and schema-8 ownership against the admitted schema-7 base.
2. Implement pure validation, nominal expansion, time resolution and planning policies, including first-valid gap/fold/date behavior.
3. Implement atomic application commands, event consumption, durable uniqueness/cursors, idempotency, conflict previews and bounded calendar queries.
4. Implement strict library/time and SQLite adapters, then compose the owned runner and queries into both real persistent runtimes.
5. Implement typed API/status facts and contract fixtures; keep actual calendar UI and HA export acceptance with their owning work.
6. Add schema migration, restore/replay, old-image refusal, compatible rollback, security evidence and operator documentation.
7. Integrate both image architectures, concurrency/crash/clock controls, full coverage, documentation, catalog and final acceptance evidence.

## 19. Definition of Done

- [ ] Every requirement has meaningful reciprocal cases and the 52-case budget is met without duplicate journey counting.
- [ ] Fixed, relative, gap/fold, exception, preview, current-authority and restore contracts agree across layers.
- [ ] Clean Architecture, strict types, security/privacy negatives and all supported first-party coverage metrics pass at 100% globally/per module.
- [ ] Every-PR CI Check executes all applicable suites on the current reviewed head, including both actual image architectures.
- [ ] Real persistent runtime composition and bounded runner lifecycle are exercised, not replaced by a helper/fixture claim.
- [ ] Documentation, actual OpenAPI, catalog, migration/rollback and original evidence scope remain truthful.
- [ ] Copilot's original format/consistency/catalog checks pass without weakened limits or source changes.
- [ ] No unresolved Bugbot finding remains before merge; report separate Copilot failures without mislabeling product failures.
- [ ] Full product/UI/HA/Stable-Edge acceptance is separately recorded before first usable release; this backend checkpoint does not complete it.
- [ ] Owned temporary resources are cleaned after retaining necessary verification and rollback evidence.

## 20. References and decisions

Sources: [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html), [Python 3.14 ZoneInfo](https://docs.python.org/3.14/library/zoneinfo.html), [dateutil rules](https://dateutil.readthedocs.io/en/stable/rrule.html), [dateutil time helpers](https://dateutil.readthedocs.io/en/stable/tz.html), and [official dateutil package](https://pypi.org/project/python-dateutil/4.0.0/). These references do not make library defaults Domus policy.

Confirmed owner defaults remain in decisions and the unchanged owner. Whole-date advancement, resource bounds and sequential schema ownership are explicit maintainer engineering choices from issue 17 answers, not separately confirmed product answers. Companion placement is approved in comment 6562344448. The Action owns its required publication and remote branch; no implementation starts on an invented branch. No Copilot or gateway modification is part of this work.