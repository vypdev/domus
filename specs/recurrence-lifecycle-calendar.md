# Relative recurrence lifecycle and protected calendar

- Status: Draft
- Date: 2026-11-03
- Catalog capability ID: recurrence-calendar
- Last verified: not applicable
- Owners: Domus maintainers; engineering and product reviewers
- Scope: Complete relative recurrence lifecycle, shared maintenance, and protected calendar behavior as a companion to the existing recurrence owners.
- Related issues/PRs: https://github.com/vypdev/domus/issues/23; PR #22; PR #24
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: none. Proposed engineering bounds require implementation evidence.

This is a proposed companion at `specs/recurrence-lifecycle-calendar.md`. Preserve `specs/recurrence-calendar.md`, `specs/recurrence-execution-foundation.md`, and `specs/recurrence-storage-continuation.md` verbatim. Their 37, 52, and four required cases remain required (93 counted cases); retained integration aliases remain unchanged and are not recounted. This draft adds its own cases only. Native SDD publication and verification of the exact Action-managed branch precede implementation. The catalog preflight and checkpoint evidence described in the issue do not establish native publication, branch readiness, or feature acceptance.

## 1. Executive summary

Deliver actual relative initial and successor work, durable source-cycle processing, fair bounded maintenance shared with fixed recurrence, reviewed schedule changes, and truthful protected calendar projections. The recommended defaults remain the retained owners’ defaults. The principal safety rule is that only current, eligible source facts and current authorization may produce effects; durable cycle closure prevents duplicate or late effects across rule changes and compatible restoration.

```text
Configure and review a relative rule -> bounded maintenance observes and validates source facts -> one durable eligible obligation is created -> authorized calendar views distinguish planned, due, and actual facts.
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Households need recurring task obligations that follow actual completed work, with an understandable calendar and recoverable review flow. The checkpoint does not yet consume relative sources into actual obligations or provide the remaining lifecycle, calendar, and UI journeys. A stored rule or passing foundation cases cannot tell a household that a successor was actually created, nor protect against duplicate or out-of-order source events.

### 2.2 Current behavior

1. The supplied immutable catalog at `8b1cbc110c389b9cdb6ecd11317c95abf2c4b0a9` identifies the three existing owners and current source paths. These paths are evidence of source locations, not proof of future behavior or framework support.
2. The issue reports that the merged checkpoint contains schema 8, fixed execution, relative creation with pristine unconsumed progress, and a fixed-only persistent runner. It lacks actual relative source materialization and the remaining lifecycle/calendar surface.
3. PR #24 merged schema 9; the issue reports current develop `8b1cbc110c389b9cdb6ecd11317c95abf2c4b0a9` contains it. Any later DDL must start from the actual supported schema 9 and use the next genuine version.
4. The issue reports a genuine schema 9 input and preserved earlier fixtures. This is not owner HA data or relative execution acceptance.

### 2.3 Evidence

- Code/catalog references: `backend/src/domus/domain/recurrence_time.py`, `backend/src/domus/application/recurrence_ports.py`, `backend/src/domus/infrastructure/recurrence_time.py`, `backend/src/domus/domain/recurrence_rules.py`, `backend/src/domus/domain/recurrence_rule_text.py`, `backend/src/domus/domain/recurrence_periods.py`, `backend/src/domus/domain/nominal_recurrence.py`, `backend/src/domus/domain/recurrence_planning.py`, `backend/src/domus/application/fixed_recurrence.py`.
- Existing owner specifications: `specs/recurrence-calendar.md`, `specs/recurrence-execution-foundation.md`, `specs/recurrence-storage-continuation.md`.
- Issue evidence: https://github.com/vypdev/domus/issues/23. Reported checkpoint hashes, test counts, reviews, database digests, and preflight results are supplied issue claims; they are not independently reverified here.
- Unknowns: actual future implementation paths, exact adapter/framework support, whether later DDL is necessary, and implementation/test evidence. These must be established during admitted implementation.

### 2.4 Retrospective classification (as-built baselines only)

Not applicable: this prospective companion does not reconstruct an implemented baseline. Current facts above are bounded to supplied catalog and issue evidence; proposed behavior below is not represented as implemented.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
|---|---|---|---|
| Authorized household manager | Configure, review, pause, resume, and change schedules | Domus UI and existing authorized commands | Task and recurrence views, review plans |
| Authorized household member | Read allowed schedule and calendar facts | Domus UI or protected HA projection | Month, week, day, and agenda |
| Composition-owned maintenance capability | Consume bounded configured work for its actual installation/channel/household | Owned runtime lifetime | Honest pending, continuation, or failure state |
| Operator | Recover compatible application/data state | Existing operations procedures | Recovery evidence and diagnostics |

A nominal identity is the stable scheduled occurrence. A source event identity is the observed task fact. A completion cycle is the immutable closure unit; record revision is mutable state. Generation identifies rule evolution. A scan position is progress evidence, not proof of effect or complete calendar freshness. Technical maintenance is a composition-owned local capability, never a human permission or caller-selected principal, installation, or channel. Actual performance, approval, planned start, and due date are separate facts.

## 4. Goals

| Requirement | Behavior |
|---|---|
| RCL-01 | Materialize the relative bootstrap and eligible successor as real task obligations; support reviewed compatible attachment/adoption without duplicating first work. |
| RCL-02 | Observe bounded live and historical source facts, persist a durable inbox and per-cycle closure, and retain successor identity across duplicates, rule changes, and compatible restoration. |
| RCL-03 | Rejection or reopening invalidates only unstarted derived successors with reason and history; downstream started/completed work survives with review attention and no fabricated effects. |
| RCL-04 | Fixed and relative work share a durable fair frontier and global 50-definition/1,000-slot budget; source scans have a separate explicit bounded budget and truthful continuation; both owned runtime lifetimes are wired. |
| RCL-05 | Support pause/resume, explicit overdue skip, reschedule exceptions, reviewed preview/apply, collision review, and safe handling of stale previews or lost responses. |
| RCL-06 | Persist task-owned timing classification, date-only/planned/deadline/actual-work facts, configurable household timing defaults, and bounded protected calendar queries. |
| RCL-07 | Protect commands, cursors, and original-operation recovery in both deployments; preserve original permissions, histories, and closed intent namespaces. |
| RCL-08 | Preserve schema 9 and supported fixtures; if new DDL is needed, use the next genuine schema version with compatible migration and rollback evidence. |
| RCL-09 | Deliver retained-case, English/Spanish UI, HA, both deployment, Stable/Edge, and all-domain acceptance with truthful documentation and quality evidence. |

### 4.1 Goals

The measurable outcomes are the nine requirements in the table above. All are required for the first usable all-domain release; foundation and checkpoint completion alone do not satisfy them.

### 4.2 Non-goals

1. Replacing or editing the three existing owning specifications.
2. Taking schema 9 ownership away from the administration continuation.
3. Changing the existing gateway, Copilot source/resources/configuration/credentials/bounds, or owner permission/history contracts.
4. HA update, release/tag/deployment, or automatic production promotion.
5. Claiming external synchronization, points, notifications, approvals, or compensation without their owning consumer and evidence.

### 4.3 Fixed product/safety invariants

1. Preserve actual-work local-calendar-day anchoring, first-valid gap and whole-date handling, one configured fold appearance, and per-task successor visibility.
2. Current authorization and original operation identity govern recovery; request data cannot choose a principal or technical scope.
3. Closure dominates duplicate/out-of-order completion or approval, including after rule changes and compatible restoration. Historical absence is not authority to create an effect.
4. Started/completed work and original history are never silently erased or fabricated. Maintenance is bounded and reports incomplete continuation truthfully.

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User/operator effect |
|---|---|---|---|
| Configure | Relative definition and pristine progress are reported | Review initial-work choice and commit one actual obligation | Household can inspect its first obligation without a duplicate manual task |
| Complete | Existing task lifecycle facts are available | Durable bounded consumer validates source and creates one eligible successor | Actual work drives an explainable due date |
| Reopen/reject | No complete relative closure consumer evidenced | Close cycle; invalidate only unstarted derived work or surface review attention | Existing downstream work and history remain visible |
| Maintain | Fixed-only persistent runner reported | Shared fair mixed frontier plus independent source-scan budget in both owned lifetimes | Pending work is bounded and continuation is inspectable |
| Observe/change | Full calendar/review surface absent | Reviewed plan/apply and protected actual/planned/due calendar | Users can see conflicts and distinguish dates and performance |

```mermaid
flowchart LR
    A[Authorized configuration] --> B[Durable bounded observation]
    B --> C[Validate current source and cycle]
    C --> D[Commit obligation and closure atomically]
    D --> E[Protected calendar and review]
    C --> F[Truthful continuation or review attention]
```

Text equivalent: authorized configuration leads to bounded observation, current-source validation, atomic obligation/closure, then protected calendar or explicit continuation/review attention.

## 6. Functional behavior and state model

### 6.1 Happy path

1. A currently authorized manager creates or reviews a relative definition and chooses the retained initial-work policy.
2. The application commits the original result and one bootstrap obligation atomically. It does not consume a completion or create ordinary manual duplicate work.
3. The owned runner scans within both independent budgets, persists exact inbox/source position, and revalidates live occurrence, cycle, rule, policy, definition, scope, and original eligibility at commit.
4. Eligible actual work creates at most one successor at original `performed_at` plus local calendar days in the snapshotted zone. Instant deadlines preserve millisecond wall time; date-only work remains a date.
5. Authorized calendar queries project actual, planned, and due facts with stable identity, masking, bounded page, and honest freshness/continuation.

### 6.2 Alternative paths

- Reviewed attachment preserves existing manual work or adopts an explicitly compatible unstarted occurrence at its exact revision. It cannot duplicate first work.
- Default `at_completion` admits current completed work pending approval; `at_verification` waits for current approval without moving the derived date. Late approval may make the successor overdue.
- Historical absent completion/approval is nonauthorizing. A closed cycle remains closed even when old events arrive after rule edits or restoration.
- Pause blocks new generation but retains assigned work. Resume previews backlog. `keep_visible` remains the default for overdue work; explicit skip records nominal identity, reason, actor, and no award.
- A rejection/reopening cancels only a still-unstarted derived successor. Started or completed downstream work remains, with durable review attention and no fabricated performance, verification, points, stock, or compensation.
- Reschedule preview identifies retained, moved, cancelled/replaced, added, and exceptional slots. Stale revisions, collisions, concurrent starts, or oversized plans require refreshed human review; no partial application is called complete.

### 6.3 State machine

| State | Entered when | User-visible meaning | Allowed next states | Recovery/owner |
|---|---|---|---|---|
| Pending observation | Durable source work remains | Some recurrence facts are not yet reconciled | Processing, attention, current | Owned runner resumes bounded frontier |
| Current | Source, policy, and revision checks pass | Eligible work may be committed | Closed, pending, attention | Application transaction and source adapter |
| Closed | Cycle is consumed, rejected, or reopened | This cycle cannot grant another effect | Closed | Durable closure invariant |
| Review attention | Collision or started downstream work needs review | Existing work is retained; a person must inspect it | Current, closed | Authorized manager reviews explicit plan |
| Paused | Manager pauses rule | Existing assignments remain; new generation stops | Active, retired | Current-authorized rule command |
| Retired | Rule is retired | No new obligations are generated | Retired | Operator preserves history |

Duplicate source identity returns the exact original outcome. Stale and out-of-order observations cannot reopen closure. Cancellation does not erase started work. A partial scan records continuation and never advances past unprocessed work.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| Horizon | Integer days | 60 local days | 7..366 | Household policy snapshot |
| Definition/slot work | Integer budgets | 50 definitions; 1,000 slots | Global across fixed and relative; minimum implementation limits must not exceed these maxima | One durable shared frontier per run |
| Period scanning | Integer rows | Existing bounded value | Existing maximum 64,000; empty periods consume work | Per run, durable continuation |
| Source scanning | Integer rows | 4,096 proposed technical default | 1..64,000 per run; every examined row, including duplicate/nonactionable/lookahead, consumes currency | Composition policy; independent from slot/period budgets |
| Source page | Integer rows | At most 100 | No more than remaining scan budget | Per bounded read; no cursor skips unprocessed rows |
| Preview expiry | Seconds | 300 | Fixed bounded expiry | Context-bound reviewed plan |
| Calendar query | Days and rows | 31 days; 25 rows | 1..366 days and 1..100 rows; half-open range | Current authorized query; 300-second context-bound cursor |
| Week start | Enum | Monday | Monday or Sunday | Private member preference; browser-neutral fallback |

Validate cross-field bounds before effects. A run admits at most 50 visited definitions and 1,000 slot work across both recurrence types. A separate source currency counts every examined row. Exhaustion yields incomplete continuation; empty source or period scans consume budget. Resume must preserve a fair durable frontier so a noisy old source cannot starve others. Retain existing RRULE, interval, time-policy, exclusion/addition, text, and horizon bounds. Missing legacy values use retained defaults; unknown values fail closed, never coercing or silently truncating. One recommended configuration is the defaults above; a meaningful alternative is a 14-day horizon with Monday week start. Safety limits, current authorization, and closure semantics are not configurable.

## 8. Clean Architecture

### 8.1 Responsibilities and dependency direction

| Layer/boundary | Owns | Must not own/import |
|---|---|---|
| Domain/pure policy | Generation, timing classification, source-cycle closure, review transitions | SQL, HA, web framework, provider DTOs |
| Application | Authorization, orchestration, fair admission, original results, bounded calendar predicates | Concrete provider SDK/process details |
| Adapters/data | Semantic source/current-proof mapping and storage mapping | Product policy or permission grants |
| Infrastructure/composition | SQLite, timezone/protocol adaptation, technical scope, clock/IDs, owned workers | Business decisions or caller-selected principal |
| Entrypoints | Input/event adaptation and trusted boundary checks | Duplicated orchestration or implicit authority |
| Presentation | Authorized view models, renderers, deliberate user intents | SQL access, mutation policy, permission transitions |

```mermaid
flowchart LR
    E[Entrypoint] --> A[Application use case]
    A --> D[Domain policy]
    A --> P[Semantic ports]
    I[SQLite and source adapters] --> P
    A --> V[Presentation model]
    W[Composition-owned workers] --> A
```

Text equivalent: entrypoints call application use cases; application depends on pure domain and semantic ports; infrastructure implements ports; presentation renders application results; composition owns workers and technical scope.

### 8.2 Contracts, state, and trust boundaries

- Pure decisions: nominal identity, eligibility, timing, closure dominance, fairness, collision and review classification.
- Application contracts: immutable bounded inputs/outputs, current grant checks, original operation identity, atomic effect/result orchestration.
- Semantic ports: current and historical source observations, current live revalidation, transactional cycle closure, task creation, protected calendar reads.
- Durable state/schema ownership: existing recurrence owners remain authoritative; any new DDL follows actual schema 9 with genuine next version and preserves fixtures 1..9. Declare and create `tests/fixtures/sqlite/v9.sql` before any future commit if that supported input is required by implementation.
- Concurrency/idempotency: unique scoped source/cycle identity, atomic receipt/effect/closure/audit/outbox, optimistic exact revisions, independent-writer and rollback evidence.
- Trust: issue/comment/source text, HA/browser inputs, cursors, and provider DTOs are untrusted. Revalidate live facts and current authorization at commit and recovery.
- Provider errors: bounded transient continuation, explicit conflict/review, safe denial, and fail-closed corruption mapping; never report uncommitted effects as complete.

### 8.3 Executable architecture constraints

Extend repository dependency/cycle and forbidden-import checks for every new runtime module and keep all authored modules within global and per-module statement/branch coverage. Contract tests must parse closed DTOs, schema ownership/version, source adapter bounds, and both runtime wiring paths. Do not infer execution support from catalog paths or fixtures.

## 9. UI/UX and content contract

### 9.1 Information hierarchy

Show current status, completed facts, next transition, required human action, impact, inspectable links, then collapsed technical evidence. A calendar entry labels planned start, due-only date, actual performance, and verification separately. Date-only values never acquire an invented time or UTC midnight.

### 9.2 Representative primary view

```markdown
# Recurrence review: kitchen filter

> **Current status:** The task was completed on 1 January; approval is pending.
>
> **Action required:** Review the proposed next due date, 31 January.

## Progress

- [x] Completion recorded from the current task cycle
- [ ] Approval and successor eligibility are pending

## What happens next

Approval may make the 31 January obligation visible. It will not change its due date.

## Links

[Open the task](...) · [Review the schedule](...)

<details><summary>Technical details</summary>Source cycle, revision, and bounded continuation evidence.</details>
```

### 9.3 Issue, PR, and comment behavior

This companion does not authorize new issue/PR automation, comments, labels, or notifications. Any implementation-facing status must use deterministic titles, one primary action, descriptive links, idempotent updates, and a bounded notification budget of zero unsolicited comments. Merge or close must not be presented as feature completion. Checks are supplemental evidence; only verified product journeys establish acceptance.

### 9.4 Accessibility, localization, and responsive behavior

Support English and Spanish with stable keys, base-language matching, and English fallback. Provide real month/week/day/agenda views, narrow-screen keyboard-accessible agenda, visible focus, non-color status, light/dark contrast, reduced motion, semantic headings/tables, and textual equivalents for visuals. Sanitize untrusted names/reasons as inert text; validate links and never render embedded commands, mentions, HTML markers, or diagrams as executable content. HA consumes the same authorized projection and stable entry identity; external synchronization is initially disabled. The existing gateway remains integrated and untouched. Do not claim an adapter exists until its actual implementation and acceptance paths are declared.

## 10. Failure, recovery, and cleanup

| Failure/partial state | User impact | Retained facts | Automatic retry | Required action | Cleanup |
|---|---|---|---|---|---|
| Source or lock unavailable | Projection is pending | Inbox, closure, original receipts, continuation | Bounded backoff | Inspect current status if persistent | Stop and join owned workers before storage closes |
| Stale preview or concurrent start | Plan cannot safely apply | Original plan and current revisions | No automatic apply | Refresh and review | Expire context-bound draft safely |
| Corrupt or conflicting evidence | Work is blocked for review | Original bytes/receipt and diagnostics | No coercion or repair | Operator follows recovery procedure | Preserve exact compatible backup |
| Response lost after commit | User may not know result | Original key, payload, result, revisions | No new-key retry | Recover original operation under current grants | Retain only original expiry/context |
| Oversized change | No complete plan is committed | Current schedule and requested draft | No partial success claim | Submit smaller reviewed plan | Keep draft until explicit correction |

Errors state impact, cause, action, and retained state in that order. A committed batch resumes from durable facts after crash. Restore preserves later processed evidence without reinstating absent effects. Current authorization precedes original-result disclosure. No automatic fresh-key replacement or POST retry. Changed verified context or logout retires private drafts.

## 11. Security, permissions, and privacy

1. Both deployment entrypoints retain current HA proof, local membership, Origin, session CSRF, expected context, and strict bounded DTO validation.
2. Request data never selects a technical actor, installation, channel, or household. Maintenance uses composition-owned actual scope.
3. Recovery maps each original action explicitly and rechecks current grants before returning private facts. Cursor principal/scope/expiry is bound; a cursor is never authentication.
4. Calendar ranges and filters are closed and bounded. Outage reads retain only original expiry and current local masking; changes remain blocked.
5. Preserve both existing closed intent namespaces and lossless int64 revisions. Do not log secrets or unnecessary household personal data. Reject replay, forged scope, stale revisions, and untrusted markup.

## 12. Observability and operational UX

- User-facing state: current, pending with continuation, review attention, paused, or safely blocked; distinguish stale projection from empty calendar.
- Operator evidence: scope, bounded run currency, visited definitions, source position, cycle identity, schema version, and safe correlation ID; no private payload dump.
- Logs/metrics: bounded counts for examined source rows, slot work, continuation age, conflicts, and worker lifecycle. Correlation never grants access.
- External dependency versus workflow failure: transient source outage is pending continuation; corrupt or unauthorized evidence is blocked/attention, not empty success.
- Rate-limit/retry: bounded exponential backoff in the retained five-second polling/backoff lifecycle; respect provider limits and stop/join workers.
- Noise budget: no unsolicited comments or notifications; one durable status update per actual state transition where a status surface exists.

## 13. Compatibility, migration, rollout, and rollback

Preserve actual schema 9, original released fixtures 1..7, genuine schema 8 input, and supported schema 9 input. Any required DDL starts from schema 9 and uses the next genuine version; never relabel an unknown development layout or infer migration acceptance from a version edit. If new DDL is unnecessary, document that with inspected evidence. Preserve in-flight rules, progress, fixed slots, relative pristine progress, original business rows, receipts, profile preferences, and closed intent contracts. Migration must be transactional, independently writable/rollback-tested, and compatible with exact application/data recovery. Roll out only through the admitted Action-owned branch and ordinary review; no release, HA update, tag, deployment, or automatic production promotion is implied. Rollback preserves original history and never fabricates or replays absent effects.

## 14. Testing strategy and numeric budget

The inventory below defines 18 new distinct cases. These are planned acceptance cases, not executed tests. The 93 retained cases from the three owning specifications remain mandatory and are not included in this companion’s derived budget. Budget areas are distinct, and each inventory row belongs to exactly one area.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Domain/configuration/pure planning | 4 | Observable scenarios in the case inventory. |
| State/application/idempotency/races | 6 | Observable scenarios in the case inventory. |
| Application use cases | 3 | Observable scenarios in the case inventory. |
| Adapters/provider contracts | 2 | Observable scenarios in the case inventory. |
| Workflows, permissions, schemas, and setup | 1 | Observable scenarios in the case inventory. |
| UI/UX/localization/sanitization | 1 | Observable scenarios in the case inventory. |
| Integration/security/migration | 1 | Observable scenarios in the case inventory. |
| Total | 18 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| recurrence-lifecycle-calendar-C01 | Domain/configuration/pure planning | RCL-01 | Relative bootstrap produces one stable nominal obligation without consuming a completion or duplicating manual first work. |
| recurrence-lifecycle-calendar-C02 | Domain/configuration/pure planning | RCL-01,RCL-05 | Compatible reviewed adoption preserves exact unstarted revision; incompatible or started work is rejected for review. |
| recurrence-lifecycle-calendar-C03 | Domain/configuration/pure planning | RCL-01,RCL-06 | Successor due date anchors to actual local work day, preserving instant wall time and date-only representation. |
| recurrence-lifecycle-calendar-C04 | Domain/configuration/pure planning | RCL-05 | Pause, resume, overdue keep-visible, and explicit skip preserve nominal identity and record reason without award. |
| recurrence-lifecycle-calendar-C05 | State/application/idempotency/races | RCL-02 | Duplicate live source observation returns the original successor identity and result. |
| recurrence-lifecycle-calendar-C06 | State/application/idempotency/races | RCL-02,RCL-07 | Out-of-order historical absent completion or approval cannot grant an effect after cycle closure. |
| recurrence-lifecycle-calendar-C07 | State/application/idempotency/races | RCL-02,RCL-08 | Independent writers race on one eligible cycle; one atomic effect and closure survive restart. |
| recurrence-lifecycle-calendar-C08 | State/application/idempotency/races | RCL-03 | Rejection/reopening cancels only unstarted derived successor and retains reason/history. |
| recurrence-lifecycle-calendar-C09 | State/application/idempotency/races | RCL-03 | Started or completed downstream work survives with review attention and no fabricated performance or compensation. |
| recurrence-lifecycle-calendar-C10 | State/application/idempotency/races | RCL-05,RCL-07 | Lost response recovers exact original result under current authorization without creating a new key. |
| recurrence-lifecycle-calendar-C11 | Application use cases | RCL-04 | Shared fixed/relative run admits no more than 50 visited definitions and 1,000 slot work with durable fair continuation. |
| recurrence-lifecycle-calendar-C12 | Application use cases | RCL-04 | Source scan counts duplicate, nonactionable, historical, and lookahead rows against its separate budget and reports continuation. |
| recurrence-lifecycle-calendar-C13 | Application use cases | RCL-05 | Reviewed preview/apply detects stale rule, policy, occurrence, and concurrent-start revisions before effects. |
| recurrence-lifecycle-calendar-C14 | Adapters/provider contracts | RCL-02,RCL-07 | Source adapter pages bounded live and historical observations, revalidates current facts, and never advances past unprocessed rows. |
| recurrence-lifecycle-calendar-C15 | Adapters/provider contracts | RCL-06,RCL-07 | Protected calendar adapter returns bounded half-open projection and context-bound cursor with current masking. |
| recurrence-lifecycle-calendar-C16 | Workflows, permissions, schemas, and setup | RCL-04,RCL-08 | Both actual owned runtime lifetimes construct and stop/join their workers; schema input is migrated from genuine schema 9 without relabeling. |
| recurrence-lifecycle-calendar-C17 | UI/UX/localization/sanitization | RCL-06,RCL-09 | English and Spanish agenda distinguish planned, due-only, actual, and approval facts with keyboard, narrow-screen, and non-color status support. |
| recurrence-lifecycle-calendar-C18 | Integration/security/migration | RCL-07,RCL-09 | Both deployment surfaces reject forged scope, stale authority, unsafe cursor, and untrusted markup while preserving original operation recovery. |

Repository-wide and changed-module statement/branch coverage must meet the repository’s supported thresholds; every authored module must reach complete supported statement and branch coverage. Pure policy requires complete branch coverage. Use deterministic clocks, IDs, fake source adapters, independent SQLite writers, rollback/restart/restore tests, and no real waits or live services. Add parsed contract checks for budgets, schemas, both deployment entrypoints, and runtime ownership. OpenAPI, browser, Storybook, real current-source images on both architectures, strict types, package, architecture, and unchanged original SDK checks apply where the implementation changes those surfaces. Manual UX evidence must review legibility, accessibility, localization, and truthful partial status. Planned cases are not evidence of execution.

## 15. Documentation and discoverability

| Path | Change |
|---|---|
| `specs/recurrence-lifecycle-calendar.md` | create |
| `specs/recurrence-calendar.md` | reference |
| `specs/recurrence-execution-foundation.md` | reference |
| `specs/recurrence-storage-continuation.md` | reference |
| `specs/catalog.json` | update |
| `specs/CATALOG.md` | update |
| `docs/product-vision.md` | update |
| `docs/architecture.md` | update |
| `docs/operations.md` | update |
| `docs/user-guide.md` | update |
| `docs/contracts/home-assistant.md` | update |
| `docs/architecture-recurrence.md` | update |
| `docs/evidence/recurrence-execution.json` | update |
| `docs/evidence/recurrence-rules.json` | update |
| `tests/fixtures/sqlite/v9.sql` | create |

The fixture is required only if implementation needs it; declare it before a future commit, preserve existing fixtures, and do not imply it exists today. Update user guidance for configuration, calendar meanings, and reviewed changes; setup guidance for permissions and both deployments; operator guidance for continuation, restore, and cleanup; contributor guidance for ports, trust boundaries, migration, and architecture checks. Keep examples synchronized with executable fixtures/contracts. Validate navigation and run `pnpm run validate:specifications`; regenerate the catalog with `pnpm run generate:specifications` when catalog metadata changes.

## 16. Acceptance

1. Given a configured relative rule with no existing compatible task, when bootstrap commits, then exactly one actual initial obligation is visible and pristine progress remains unconsumed.
2. Given current eligible completion at a local-day boundary, when bounded maintenance commits, then one successor has the correct actual-work-derived date and stable identity.
3. Given duplicate, delayed, or historical absent source facts after closure, when observed across rule edits or compatible restore, then no second effect is created and the original closure remains inspectable.
4. Given rejection or reopening, when reconciliation runs, then only unstarted derived work is invalidated; started/completed work retains its facts and receives review attention without fabricated compensation.
5. Given both fixed and relative backlogs, when a run exhausts either work budget, then the shared definition/slot limits and separate scan limit are respected and durable fair continuation is visible.
6. Given a stale preview or a concurrent start, when apply is attempted, then no stale destructive change commits and the user is asked to refresh and review.
7. Given a lost response after a committed command, when the authorized user recovers the original operation, then the exact original result is returned only after current permission checks.
8. Given a protected bounded calendar request, when the user selects a range, then date-only, planned, due, actual, and approval facts remain distinct and unauthorized or stale cursors reveal no data.
9. Given keyboard-only use in English or Spanish on a narrow viewport, when the agenda is reviewed, then focus, labels, status, and next action remain understandable without color or pointer input.
10. Given a genuine schema 9 input and supported fixtures, when a required migration runs, then it preserves original business rows, receipts, recurrence state, and rollback evidence without relabeling unknown layouts.
11. Given the exact admitted Action-owned branch, when implementation is proposed for merge, then every retained and new acceptance case has actual evidence, current-source images and applicable CI checks pass, no unresolved Bugbot finding remains, and no lifecycle label is misrepresented as full feature acceptance.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| RCL-01 | recurrence-lifecycle-calendar-C01, recurrence-lifecycle-calendar-C02, recurrence-lifecycle-calendar-C03 |
| RCL-02 | recurrence-lifecycle-calendar-C05, recurrence-lifecycle-calendar-C06, recurrence-lifecycle-calendar-C07, recurrence-lifecycle-calendar-C14 |
| RCL-03 | recurrence-lifecycle-calendar-C08, recurrence-lifecycle-calendar-C09 |
| RCL-04 | recurrence-lifecycle-calendar-C11, recurrence-lifecycle-calendar-C12, recurrence-lifecycle-calendar-C16 |
| RCL-05 | recurrence-lifecycle-calendar-C02, recurrence-lifecycle-calendar-C04, recurrence-lifecycle-calendar-C10, recurrence-lifecycle-calendar-C13 |
| RCL-06 | recurrence-lifecycle-calendar-C03, recurrence-lifecycle-calendar-C15, recurrence-lifecycle-calendar-C17 |
| RCL-07 | recurrence-lifecycle-calendar-C06, recurrence-lifecycle-calendar-C10, recurrence-lifecycle-calendar-C14, recurrence-lifecycle-calendar-C15, recurrence-lifecycle-calendar-C18 |
| RCL-08 | recurrence-lifecycle-calendar-C07, recurrence-lifecycle-calendar-C16 |
| RCL-09 | recurrence-lifecycle-calendar-C17, recurrence-lifecycle-calendar-C18 |

Retained traceability remains in the three existing owner documents; this companion neither copies nor regenerates their inventories. The derived table above must link every RCL requirement to exactly the full case IDs in the inventory, with no unowned or undefined IDs.

## 18. Implementation sequence

1. Publish this companion through the supported native `companion` action for capability `recurrence-calendar`; preserve the three existing owners byte-for-byte and verify the Action-owned ref.
2. Verify the actual current development base and branch lifecycle. Do not implement on bootstrap master or a contributor replacement ref.
3. Establish pure timing, eligibility, closure, fairness, and review policies with complete branch coverage.
4. Implement durable source inbox, atomic cycle closure, task effects, and exact original-operation recovery; exercise independent-writer, rollback, restart, and restore behavior.
5. Implement shared maintenance budgets, separate source scanning, and both composition-owned runtime lifetimes.
6. Implement reviewed changes, timing classification, protected calendar projections, UI, HA consumption, English/Spanish content, and both deployment acceptance.
7. Complete migration only if required, preserving genuine schema 9 and fixtures; finish documentation, catalog evidence, security, human UX review, and all applicable CI gates.

Do not declare a planned acceptance case executed until its implementation evidence is present. No implementation begins before native SDD publication and exact managed branch verification.

## 19. Definition of Done

- [ ] Every RCL requirement and all retained owner requirements have acceptance and reciprocal traceability.
- [ ] Existing owners remain verbatim; their 93 counted cases and integration aliases remain required and unchanged.
- [ ] Architecture boundaries and executable dependency, DTO, schema, and runtime wiring checks pass.
- [ ] The numeric budget and all inventory cases pass; repository and changed-module coverage thresholds pass, with complete supported statement/branch coverage per authored module.
- [ ] Shared and source budgets are separately enforced, fair, durable, and report truthful continuation in both owned runtime lifetimes.
- [ ] Current authorization, source eligibility, closure, original operation recovery, history, and restore invariants pass.
- [ ] Calendar and review UI, English/Spanish, accessibility, responsive, sanitization, and HA projection acceptance pass in applicable surfaces.
- [ ] Migration starts from genuine supported schema 9 if needed and preserves fixtures and rollback evidence.
- [ ] User, setup, operator, contributor, migration, and troubleshooting documentation is discoverable and validated.
- [ ] Required generated artifacts and applicable OpenAPI/browser/Storybook, architecture, package, type, image, and CI checks pass; no unresolved Bugbot finding remains.
- [ ] `specs/catalog.json` evidence and `specs/CATALOG.md` are current and `pnpm run validate:specifications` passes.
- [ ] No readiness-blocking decision remains unresolved; no release, deployment, HA update, or promotion is inferred.

## 20. References and decisions

- Primary sources: supplied immutable catalog at `8b1cbc110c389b9cdb6ecd11317c95abf2c4b0a9`; issue https://github.com/vypdev/domus/issues/23; repository specification standard and template.
- Related specifications: `specs/recurrence-calendar.md`, `specs/recurrence-execution-foundation.md`, `specs/recurrence-storage-continuation.md`.
- Related work: issue #20 continuation; PR #22 checkpoint; PR #24 schema 9 merge; upstream admission recovery evidence at https://github.com/vypdev/copilot/issues/763#issuecomment-6613738740.
- Decisions: use the supported companion route for the existing `recurrence-calendar` capability and new path `specs/recurrence-lifecycle-calendar.md`; preserve owners verbatim; retain all original product policies; use schema after 9 only if later DDL is required.
- Rejected alternatives: replacing an existing owner, recounting retained cases, inferring execution from test counts or lifecycle labels, taking schema 9 ownership from the administration continuation, or treating a bounded checkpoint as full acceptance.
- Follow-up outside this spec: any later product decision genuinely required by implementation must be recorded and block readiness until resolved; none is presently identified.