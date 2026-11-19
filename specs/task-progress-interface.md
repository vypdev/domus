# Start, block and unblock tasks from Tasks

- Status: Draft
- Catalog capability: household-tasks

## 1. Executive summary

Add Start, Block, and Unblock actions to the existing Tasks workspace so members can make eligible work visible as in progress, record why work is blocked, and deliberately resume blocked work. Show the saved blocking reason beside a blocked task. Preserve the selected task’s assignees and use current server-provided transition hints, current command authority, and the exact reviewed revision for every change. The retained contracts and cases in `specs/household-tasks.md`, `specs/task-execution-foundation.md`, `specs/household-task-categories.md`, and `specs/task-assignment-interface.md` remain authoritative; this companion specifies the progress interface delta.

```text
Open task -> review current actions -> choose Start, Block, or Unblock -> review any conflict -> deliberately save -> see current task state and, when blocked, its saved reason
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Members can manage tasks in the existing Tasks workspace, but cannot use it to start assigned work, explain a blocker, or resume blocked work. The interface also needs to preserve the reason and proposed change through validation errors, concurrent updates, and interrupted responses so members can tell what was saved and what still needs action.

### 2.2 Current behavior

The selected source includes the task workspace and presentation, controller, HTTP adapter, and journal boundaries documented by the existing task contracts. The issue describes task transitions and current action hints as existing backend capabilities, while this interface delta is prospective. The selected source evidence cited here does not independently establish every backend transition behavior; the retained execution contract remains the authority for lifecycle and command semantics.

The selected tree contains `frontend/src/presentation/domus-task-overview.ts` and `frontend/src/presentation/domus-automation-execution.ts` as presentation references. The issue identifies `@vypdev/ha-ui` version `0.1.0-next.2` as the intended released component package, pinned through `frontend/package.json` and `pnpm-lock.yaml`; its use for this delta is a proposed implementation constraint, not evidence of completed integration.

### 2.3 Evidence

The retained task lifecycle, authorization, revision, receipt, and history contracts are in `specs/household-tasks.md` and `specs/task-execution-foundation.md`; the existing Tasks assignment journey is in `specs/task-assignment-interface.md`. The catalog registers task presentation evidence including `frontend/src/presentation/domus-task-overview.ts`. `specs/README.md` defines the specification and catalog publication goals. No implementation, acceptance run, or publication outcome for this proposed delta is asserted here.

## 3. Actors, surfaces, and terminology

Household members use the existing Tasks workspace to act on a selected task occurrence. The selected task’s current detail and action hints determine which progress actions are offered. The existing task command remains responsible for enforcing lifecycle policy, household scope, revision, and authority; the interface is not an authorization boundary.

“Start” moves assigned work to In progress. “Block” moves eligible Available, Assigned, or In progress work to Blocked and requires a reason. “Unblock” moves blocked work to Assigned when its current assignee set is nonempty, or to Available when it is empty. “Current hint” means the action advertised for the selected task after refreshing its current details; a stale hint alone never authorizes a change. “Blocking reason” is the exact submitted text saved as the task’s current `state_reason` while blocked. “Selected occurrence identity” and “revision” identify the task and version the member reviewed before acting.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

Let a member start an assigned task only when the current `transition:in_progress` hint is present. Let a member block an Available, Assigned, or In progress task only when the current `transition:blocked` hint is present. Let a member unblock a blocked task to Assigned when current assignees exist, or to Available when none exist, and require the matching current target hint. Preserve assignee identities. Enforce current `tasks.complete` authority for In progress, Blocked, and Assigned targets, and `tasks.manage` authority for Available.

For blocking, require meaningful valid multiline text within the existing 1000 Unicode code point limit, validated with `validate_task_text(multiline=True, required=True)`. Preserve the exact valid submission and a correctable draft across validation errors and recoverable failures. Reject blank reasons, invalid Unicode, disallowed controls, and over-limit text. Show the saved reason as text to permitted readers while the task is blocked, with accessible labels, instructions, and errors. Start and Unblock use the existing empty reason string; the historical blocking reason remains in its receipt and history.

Before admitting an action, capture the selected occurrence identity, target, reason, and revision, then refresh current session, scope, task detail, and action hints through the existing controller path. A changed revision or competing post-admission conflict must retain the proposed target and reason and show current facts. Require explicit review and a separate deliberate save at the reviewed revision while the target remains permitted. If the target is unavailable, offer refresh or cancel and require a deliberate new choice. Follow existing protected-view retirement behavior when authority is revoked. Direct writes must transactionally recheck current command authority and exact revision.

### 4.2 Non-goals

This delta does not redefine task lifecycle, transition policy, authorization, receipts, history, or journal semantics, and does not replace the retained task owners. It does not introduce new task states, broaden available actions, or let the client’s visible controls grant authority.

### 4.3 Fixed product/safety invariants

Current server state and command checks govern every mutation; hints are not authority. A rejected or conflicted action must not silently change the task or discard the member’s proposed target or reason. Any interrupted request remains bound to its original key, action, body, and scope; recovery must use the existing recorded-authorization boundary, produce at most one transition/history/receipt, and reject a changed payload under the same key. Keep current task facts distinct from any recovered historical result, including after restore. Preserve the existing prepared/uncertain request gate and compatibility with prior creation and assignment journal entries.

Publication completion requires that the specification satisfy the required format, that internal and cross-document consistency is checked, and that reciprocal catalog ownership, paths, and evidence agree with the generated view. These are publication constraints, not product goals or claims that checks have run.

| Requirement | Behavior |
| --- | --- |
| SDD-I143-U4-R1 | The increment MUST follow the existing CI acceptance gates and preserve the configured self-hosted runner placement and full released action versions. |
| SDD-I143-U6-R1 | Start transitions an assigned task to in_progress only when the current transition:in_progress hint is present. |
| SDD-I143-U6-R2 | Block transitions an available, assigned, or in_progress task to blocked only when the current transition:blocked hint is present. |
| SDD-I143-U6-R3 | Unblock transitions a blocked task to assigned when its current assignee set is nonempty, or to available when that set is empty; it requires the matching current transition:<target> hint. |
| SDD-I143-U6-R4 | Start, block, and unblock preserve assignee identities and use current authorization: tasks.complete for in_progress, blocked, and assigned targets, and tasks.manage for available. |
| SDD-I143-U7-R1 | Blocking requires meaningful valid multiline text within the existing 1000 Unicode code point maximum, validated with validate_task_text(multiline=True, required=True); preserve the exact valid submission, reject blank required reasons, invalid Unicode, and disallowed controls, and preserve a correctable draft across validation and recoverable failures. |
| SDD-I143-U8-R1 | A start, block, or unblock action captures the selected occurrence identity, target, reason, and revision; refreshes current session, scope, task detail, and action hints through the existing controller path before admission; and never treats a stale hint as authority. |
| SDD-I143-U8-R2 | On a changed revision or competing post-admission conflict, retain the proposed target and reason and show current facts; require explicit review followed by a separate deliberate save at the reviewed revision while the target remains permitted. |
| SDD-I143-U8-R3 | When a target is unavailable, offer refresh or cancel and require a deliberate new choice; when authority is revoked, follow existing protected-view retirement behavior. |
| SDD-I143-U8-R4 | Recheck current command authority and exact revision transactionally for direct writes. |

## 5. Current versus proposed product journey

The retained task lifecycle, transition policy, assignment, authorization, revision, receipt, and history contracts remain in `specs/household-tasks.md` and `specs/task-execution-foundation.md`. This companion adds controls to the existing Tasks experience: members can start assigned work, block eligible work with a reason, and deliberately unblock it according to the task’s current assignee set.

| Stage | Current Tasks experience | Proposed Tasks experience | User effect |
|---|---|---|---|
| Find and select | The task overview groups work and emits a selection intent for an occurrence. | Keep that entry point; show permitted progress actions with the selected task’s current state and action hints. | The member can see which actions are currently offered for this occurrence. |
| Start or block | The interface does not offer these transitions from Tasks. | Start assigned work, or block available, assigned, or in-progress work. Blocking requires a meaningful multiline explanation. | Work status and the reason it cannot proceed are visible to permitted readers. |
| Unblock | The interface does not offer this transition from Tasks. | Explicitly choose the currently permitted target: assigned when assignees remain, otherwise available. | The member understands whether responsibility remains with the existing assignees or work becomes available. |
| Resolve changes and observe | The retained command contract governs revision conflicts and original-request receipts. | Refresh facts before admission; on conflict preserve the proposed action and reason for review, and recover uncertain requests using their frozen original request. | A stale action cannot silently apply, and a retry cannot create a second transition. |

Flow: select occurrence -> refresh session, scope, detail, and hints -> choose an offered action -> review and deliberately save -> see the current result or review/recover. A changed revision or competing conflict requires reviewing current facts and a separate deliberate save. An unavailable target requires refresh or cancel and a new deliberate choice. Revoked authority follows the existing protected-view retirement behavior.

## 6. Functional behavior and state model

### Normal transitions

- Start is available only for an assigned task with the current `transition:in_progress` hint. It moves the task to `in_progress` and preserves assignee identities.
- Block is available only for an available, assigned, or in-progress task with the current `transition:blocked` hint. It moves the task to `blocked`, preserves assignee identities, and saves the exact validated reason as the current `state_reason`.
- Unblock is available only for a blocked task and the matching current hint. With a nonempty current assignee set, `transition:assigned` returns it to `assigned`; with an empty set, `transition:available` returns it to `available`. Preserve assignee identities.
- Start, block, and unblock use the retained transition command and state policy. Start and unblock submit the existing empty reason, clearing the current reason through the accepted transition. Historical reasons remain in their original receipt and history.
- Current authorization is target-specific: `tasks.complete` is required for `in_progress`, `blocked`, and `assigned` targets; `tasks.manage` is required for `available`. A visible control or stale hint grants no authority.

### Blocking reason and feedback

Require meaningful multiline text validated with `validate_task_text(multiline=True, required=True)` and the existing 1000 Unicode code point maximum. Reject blank required reasons, invalid Unicode, disallowed controls, and over-limit input. Preserve valid submitted text exactly. Preserve the correctable draft after validation errors and recoverable failures. Render the saved current reason as text beside the blocked state for permitted readers, with associated accessible labels, instructions, and errors.

Show clear loading, unavailable, denied, invalid, conflict, uncertain, and confirmed states. On conflict, show current task facts without discarding the proposed target or reason; require explicit review and then a separate deliberate save at the reviewed revision while the target remains permitted. If the target is no longer available, offer refresh or cancel and require a new action choice. Do not imply an unconfirmed transition succeeded.

The task overview in `frontend/src/presentation/domus-task-overview.ts` already groups tasks and emits occurrence selection intents. The existing bilingual presentation in `frontend/src/presentation/domus-automation-execution.ts` demonstrates released button, card, and feedback components and localized status/action rendering; use the declared `@vypdev/ha-ui` package version in `frontend/package.json` and lockfile. Keep keyboard focus, readable labels, and narrow touch layouts usable in English and Spanish.

## 7. User-facing configuration

This interface increment adds no user-configurable settings. Keep the blocking reason’s existing fixed 1000 Unicode code point limit and validator behavior; it is a correctness and safety constraint, not a preference. Keep action eligibility, target selection, and authorization derived from current task facts and server-provided hints. Do not let users configure transition rules, permissions, revision checks, or request-recovery behavior.

## 8. Clean Architecture design

### Responsibilities and dependency direction

| Boundary | Responsibility for this delta | Must not own |
|---|---|---|
| Domain | Retained `TaskOccurrence` transition policy and `next_occurrence_state` rules determine valid state changes and reason semantics. | UI visibility, provider or DOM concerns. |
| Application | Reuse the existing task transition command, current authorization, exact revision check, receipt, history, and transaction boundary. | Duplicated presentation policy or provider DTOs. |
| Adapters and infrastructure | Preserve existing persistence, composition, and original-request recovery boundaries; map outcomes to semantic results. | Client-selected authority or relaxed revision checks. |
| Entrypoint/controller | Refresh current session, scope, task detail, and action hints before admitting an action; bind the request to the selected occurrence and frozen original request. | Treating a cached hint as authorization or rebuilding a changed request for replay. |
| Presentation | Render current state, permitted actions, reason editor, review/conflict, uncertainty, and result; emit user intents. | Performing mutations or deciding authorization. |

The existing architecture contract in `specs/task-execution-foundation.md` keeps pure task policy in Domain, orchestration and semantic ports in Application, provider/storage details outside those layers, and presentation limited to view models and rendering. Preserve those dependency directions in both supported compositions.

### Request, concurrency, and trust boundaries

Capture the selected occurrence identity, target, reason, and revision. Before admission, use the existing controller path to refresh session, scope, detail, and action hints. Direct writes must transactionally recheck current command authority and exact revision. A stale revision or competing post-admission conflict retains the proposal and displays current facts; only explicit review followed by a separate deliberate save may proceed at the reviewed revision while the target remains permitted.

Prepare the task journal with its original key, canonical body, selected revision, and verified installation, channel, actor, and household scope before explicit send. For an interrupted or unbound response, keep the outcome uncertain and check the existing original-request endpoint with the same frozen key, action, and body binding. Extend its typed workspace allowlist for `task.transition` through `recorded_authorization`; repeated protected reads return the same recorded operation. Exact replay creates one transition, history entry, and receipt; a changed payload under that key conflicts. Show current task facts separately from a recovered historical result, including after activated restore. Preserve the prepared/uncertain request gate and journal compatibility with prior creation and assignment entries. Only an explicit deliberate save initiates a new transition.

If authority is revoked, follow existing protected-view retirement behavior. Treat task input and returned facts as untrusted at presentation boundaries; render reasons as text and preserve household scoping. Keep schema 34 if implementation confirms existing persisted formats cover this change; migration needs remain subject to implementation evidence.

### Verification constraints

Preserve the existing CI acceptance gates, configured self-hosted runner placement, and full released action versions. The selected source declares the frontend package manager and scripts in `frontend/package.json`; declaration alone does not establish execution or specification coverage. Follow the existing task browser journeys and applicable container jobs, with acceptance covering Ingress and standalone, both CPU images, English keyboard and Spanish narrow touch journeys, and an immutable installed Edge candidate. The precise invocation and prerequisites for SDD format, consistency, catalog, and product validation remain unverified here; require those observable outcomes without treating a different documentation check as SDK consistency verification. Do not infer passing acceptance from command declarations.

## 9. UI/UX and content contract

### UI/UX and content contract

Add start, block, and unblock actions to the existing Tasks detail experience. Render only actions permitted by the current task detail and transition hints. Show the current task state and assignees, then the available action and any required reason. While blocked, show the saved current `state_reason` as readable text to permitted task readers. Start and unblock submit the existing empty reason value; a successful transition clears the current reason while its historical value remains in the existing receipt and history.

Blocking uses a labeled multiline reason editor. Explain that a reason is required and limited to 1000 Unicode code points. Preserve a valid entered draft if validation or a recoverable request failure prevents saving. Associate instructions and validation errors with the editor, expose errors in text, and do not rely on color alone. The existing task interface owns the shell and interaction boundaries in `specs/task-assignment-interface.md`; the selected presentation examples in `frontend/src/presentation/domus-task-overview.ts` and `frontend/src/presentation/domus-automation-execution.ts` demonstrate the project's task overview and button, card, feedback, focus, and bilingual presentation patterns.

Use one clear primary action at a time. Confirmation must identify the task, proposed state, reason when present, and revision being saved. Conflict review presents current facts and the retained proposal; the user reviews those facts and then makes a separate deliberate save. If the target is no longer available, offer refresh or cancel and require a new deliberate choice. Present pending, unavailable, denied, rejected, conflict, uncertain, recovered historical result, and completed states in plain language, separating current task facts from historical operation results. Keep diagnostics secondary and omit protected details after access is revoked.

Use the existing English and Spanish locale behavior and provide keyboard operation, visible focus, programmatic labels, and readable narrow-screen layouts. Controls and feedback should follow the released `@vypdev/ha-ui` contracts already used by the selected presentation components; retain the existing task shell and multiline reason semantics.

## 10. Failure, recovery, and cleanup

### Failure, recovery, and cleanup

A validation failure leaves the task unchanged and preserves the editable reason for correction. A rejected or unavailable request must state its impact, cause, next action, and retained draft. Do not report a transition as failed after a committed result has been recovered.

Before admission, refresh the current session, household scope, task detail, and action hints through the existing controller path. A stale hint alone never admits a command. On revision change or a competing post-admission conflict, retain the proposed target and exact reason, display current task facts, and require explicit review followed by a separate save against the reviewed revision if the target remains permitted. If the target becomes unavailable, offer refresh or cancel; do not select a replacement automatically. If authority is revoked, use the existing protected-view retirement behavior.

Prepare the task journal with the original request key, canonical body, selected revision, and verified installation, channel, actor, and household scope before sending. Treat interrupted or unbound responses as uncertain. On reload or restart, recover through the existing original-request endpoint with the same frozen key, action, body, and authorization binding; extend its typed workspace allowlist for the existing `task.transition` action through recorded authorization. Repeated protected original reads return the same recorded operation. Exact replay produces one transition, history entry, and receipt; a changed payload under that key conflicts. Show current task facts separately from a recovered historical result, including after activated restore. Only an explicit deliberate save starts a new transition. Preserve the prepared/uncertain request gate and compatibility with earlier creation and assignment journal entries.

## 11. Security, permissions, and privacy

### Security, permissions, and privacy

Transition hints describe current permitted actions but do not grant authority. The server remains authoritative: it rechecks current command authority and exact revision transactionally for direct writes. Preserve assignee identities. Require `tasks.complete` for in-progress, blocked, and assigned targets, and `tasks.manage` for the available target. Unblock chooses assigned only when the current assignee set is nonempty; otherwise it chooses available and requires the corresponding current transition hint.

Treat reason text and all client-supplied task, revision, target, and journal data as untrusted. Validate blocking text with the existing `validate_task_text(multiline=True, required=True)` semantics: require meaningful valid multiline text within 1000 Unicode code points and reject blank required reasons, invalid Unicode, and disallowed controls. Preserve valid submitted text exactly. Render saved and proposed reasons as text, not executable markup. A journal record or cached hint is recovery context, never authorization. Original-operation reads retain transaction-time grants and the recorded authorization boundary. On revocation, retire the protected view and do not disclose task or member details no longer authorized.

## 12. Observability and operational UX

### Observability and operational UX

Show users the current task state, the action outcome, and whether review, refresh, correction, or recovery is required. Keep operation identity and revision available in the existing authorized receipt/history experience; distinguish the current task from a historical recovered result. Do not expose reason text or task details to unauthorized readers. Operational diagnostics should identify the operation and sanitized failure category without copying protected request content into logs or user-facing diagnostics.

Acceptance evidence must exercise start, block, both unblock destinations, validation and draft retention, changed-revision and competing-conflict review, unavailable targets, authority retirement, exact replay, changed-payload conflict, and transactional rejection of stale revision or revoked authority. Validate English keyboard and Spanish narrow-touch journeys, plus supported ingress and standalone coverage, both CPU images, and an immutable installed Edge candidate. Follow the existing CI acceptance gates and preserve configured self-hosted runner placement and full released action versions. The selected tree includes `frontend/tests/e2e/tasks.spec.ts` and `.github/workflows/ci_check.yml`; their complete applicability to this new increment and the concrete installed Edge invocation remain to be verified during implementation.

## 13. Compatibility, migration, rollout, and rollback

### Compatibility, migration, rollout, and rollback

Keep the existing task states, transition policy, receipts, history, authorization, and journal recovery semantics as the owning contract in `specs/household-tasks.md`, `specs/task-execution-foundation.md`, and `specs/task-assignment-interface.md`. This companion defines only the Tasks interface delta. Preserve schema 34 if implementation evidence confirms existing persisted formats cover the change; otherwise document the required migration and restart/restore behavior before readiness. Journal changes must continue to read prior creation and assignment entries and must not reinterpret an uncertain original request as permission to issue a new command.

Qualify the increment on supported ingress and standalone surfaces, English keyboard and Spanish narrow touch journeys, both CPU images, and an immutable installed Edge candidate. Follow existing installation and operations guidance in `docs/installation-home-assistant.md` and `docs/operations.md`; keep rollback compatible with the existing paired application and database restore approach. The concrete migration need, rollout procedure, rollback evidence, and invocation/prerequisites for installed acceptance remain unverified in the selected source and must be resolved as implementation outcomes.

## 14. Testing strategy and numeric budget

The minimum distinct-case budget is ten, with one case for each defined scenario in the host-maintained inventory; repeated executions do not increase the count. Cover the three state transitions and their current authorization, blocking-reason validation and draft retention, refreshed admission and stale-hint rejection, revision and competing-write review, unavailable targets and revoked authority, transactional command checks, and the configured CI acceptance gates. Exercise normal UI paths and direct writes, including invalid input, recovery after recoverable failure, and current versus historical task facts. The retained contracts and cases in `specs/household-tasks.md`, `specs/task-execution-foundation.md`, `specs/household-task-categories.md`, and `specs/task-assignment-interface.md` remain authoritative references; this companion does not redefine them. The selected project declares `pnpm@10.34.0` and Node `>=24.20.0 <25` in root `package.json`; frontend scripts are declared in `frontend/package.json`. `specs/README.md` names `pnpm run validate:specifications` and `pnpm run generate:specifications`, but the validator definitions and execution prerequisites were not inspected here. Their availability and scope therefore remain unverified. Do not treat a declaration as execution or passing evidence. Validate this specification’s required format and internal and cross-document consistency as outcomes; retain actual applicable product and CI acceptance evidence with its observed scope.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| workflows/setup/schema | 1 | Observable scenarios in the case inventory. |
| start | 1 | Observable scenarios in the case inventory. |
| block | 1 | Observable scenarios in the case inventory. |
| unblock | 2 | Observable scenarios in the case inventory. |
| blocking reason | 1 | Observable scenarios in the case inventory. |
| task-progress-interface | 4 | Observable scenarios in the case inventory. |
| Total | 10 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| inventory4-C01 | workflows/setup/schema | SDD-I143-U4-R1 | The increment's CI workflow retains the configured self-hosted placement and full released action versions, and its acceptance run exercises the existing task browser journeys and applicable container jobs. |
| inventory6-C01 | start | SDD-I143-U6-R1, SDD-I143-U6-R4 | Starting an assigned task with the current transition:in_progress hint changes its state to in_progress, preserves assignee identities, and requires tasks.complete authority. |
| inventory6-C02 | block | SDD-I143-U6-R2, SDD-I143-U6-R4 | Blocking an available, assigned, or in_progress task with the current transition:blocked hint changes its state to blocked, preserves assignee identities, and requires tasks.complete authority. |
| inventory6-C03 | unblock | SDD-I143-U6-R3, SDD-I143-U6-R4 | Unblocking a blocked task with a nonempty current assignee set and transition:assigned hint changes its state to assigned, preserves assignee identities, and requires tasks.complete authority. |
| inventory6-C04 | unblock | SDD-I143-U6-R3, SDD-I143-U6-R4 | Unblocking a blocked task with an empty current assignee set and transition:available hint changes its state to available and requires tasks.manage authority. |
| inventory7-C01 | blocking reason | SDD-I143-U7-R1 | Submit valid multiline text and verify the exact text is saved as current state_reason and shown to permitted readers while blocked; verify blank, invalid Unicode, disallowed controls, and over-limit text are rejected, with the draft preserved for correction after validation and recoverable failure. |
| inventory8-C01 | task-progress-interface | SDD-I143-U8-R1 | For start, block, and unblock, inspect the admitted action and confirm it records the selected occurrence identity, target, reason, and revision after the existing controller path refreshes current session, scope, task detail, and action hints; a stale hint alone does not admit the action. |
| inventory8-C02 | task-progress-interface | SDD-I143-U8-R2 | Change the revision and separately create a competing post-admission conflict; each outcome retains the proposed target and reason and displays current facts, and saving is unavailable until explicit review followed by a separate deliberate save at the reviewed revision while the target is permitted. |
| inventory8-C03 | task-progress-interface | SDD-I143-U8-R3 | Make the selected target unavailable and confirm refresh and cancel are offered and no replacement is selected without deliberate new choice; revoke authority and confirm the existing protected-view retirement behavior occurs. |
| inventory8-C04 | task-progress-interface | SDD-I143-U8-R4 | Attempt direct writes with stale revision and with revoked or otherwise non-current command authority; each is rejected transactionally, while a write with current authority and exact revision is accepted. |

## 15. Documentation and discoverability

Document the Tasks journey for starting assigned work, explaining a block, and deliberately resuming blocked work. Explain the visible state and saved blocking reason, current action availability, conflict review, correction of a reason draft, and what happens when authority or a target changes. Provide accessible, localized English keyboard and Spanish narrow-touch guidance. Keep state, transition, and authorization rules in the retained owners, including `specs/household-tasks.md` and `specs/task-execution-foundation.md`; this companion describes only the interface and recovery delta. The selected project pins `@vypdev/ha-ui` at `0.1.0-next.2` in `frontend/package.json` and `pnpm-lock.yaml`. Existing presentation examples are `frontend/src/presentation/domus-automation-execution.ts` and `frontend/src/presentation/domus-task-overview.ts`. Use the released button, feedback, and card contracts for progress controls and the existing multiline reason control and text validation semantics. Render the saved reason as text for permitted readers while blocked. The companion specification at `specs/task-progress-interface.md` is a proposed create, not an existing file.

| Path | Change |
| --- | --- |
| frontend/package.json | reference |
| pnpm-lock.yaml | reference |
| frontend/src/presentation/domus-automation-execution.ts | reference |
| frontend/src/presentation/domus-task-overview.ts | reference |
| specs/task-progress-interface.md | create |

[frontend/package.json](../frontend/package.json) · [pnpm-lock.yaml](../pnpm-lock.yaml) · [frontend/src/presentation/domus-automation-execution.ts](../frontend/src/presentation/domus-automation-execution.ts) · [frontend/src/presentation/domus-task-overview.ts](../frontend/src/presentation/domus-task-overview.ts) · [specs/task-progress-interface.md](task-progress-interface.md)

## 16. Acceptance scenarios

These are prospective acceptance outcomes, not claims of implementation or execution.

1. In Tasks, start an assigned task only when the current `transition:in_progress` hint is present. The state becomes `in_progress`, assignee identities remain unchanged, and current `tasks.complete` authority is required. (inventory6-C01)
2. For available, assigned, or in-progress work, block only when the current `transition:blocked` hint is present. Preserve assignee identities and require `tasks.complete` authority for the blocked target. (inventory6-C02)
3. Require meaningful multiline block text within the existing 1000 Unicode code-point maximum, validated with `validate_task_text(multiline=True, required=True)`. Preserve the exact accepted text as `state_reason` and show it as text to permitted readers while blocked. Reject blank required text, invalid Unicode, disallowed controls, and over-limit input; retain a correctable draft after validation or recoverable failure. (inventory7-C01)
4. Unblock a task with current assignees to `assigned` only with `transition:assigned`; unblock one without assignees to `available` only with `transition:available`. Preserve assignee identities and enforce `tasks.complete` for the assigned target and `tasks.manage` for the available target. Start and unblock use the existing empty reason behavior; the historical block reason remains in its receipt and history. (inventory6-C03, inventory6-C04)
5. For each action, capture the selected occurrence identity, target, reason, and revision. Refresh session, scope, task detail, and action hints through the existing controller path before admission. A stale hint alone never admits an action. (inventory8-C01)
6. On changed revision and, separately, a competing post-admission conflict, retain the proposed target and reason and show current facts. Require explicit review and then a separate deliberate save at the reviewed revision while the target remains permitted. (inventory8-C02)
7. If the target is unavailable, offer refresh or cancel and require a deliberate new choice without silently selecting a replacement. If authority is revoked, follow the existing protected-view retirement behavior. (inventory8-C03)
8. Reject direct writes transactionally when command authority is revoked or otherwise not current, or the revision is not exact; accept a write with current authority and exact revision. (inventory8-C04)
9. The increment retains the existing CI workflow’s configured self-hosted placement and full released action versions; its acceptance run exercises the existing task browser journeys and applicable container jobs. (inventory4-C01)

The selected project’s current suite, installed Edge qualification, and complete supported-coverage evidence remain prospective acceptance evidence for this increment; this draft does not claim they have been run for it.

## 17. Requirements traceability

The host-maintained traceability inventory maps each requirement only to cases that exercise it, reciprocally with the case definitions. Start state, current transition hint, assignee preservation, and `tasks.complete` authority map to inventory6-C01. Blocking state, hint, assignee preservation, and authority map to inventory6-C02. Unblock target selection from the current assignee set and target-specific hint and authority map to inventory6-C03 and inventory6-C04. Blocking-text validation, exact saved reason, permitted display, and correctable draft map to inventory7-C01. Refreshed action admission and rejection of stale hints map to inventory8-C01. Changed-revision and competing-write review map to inventory8-C02. Unavailable target handling and revoked-authority retirement map to inventory8-C03. Transactional current-authority and exact-revision enforcement maps to inventory8-C04. CI workflow placement, action versions, and acceptance-job coverage map to inventory4-C01. Existing owning case IDs remain references, never new definitions. Structural counts and reciprocal mappings establish inventory consistency only, not semantic completeness or executed acceptance.

Publication acceptance must make all three outcomes observable: the specification satisfies the required format; internal and cross-document consistency is checked; and reciprocal catalog ownership, paths, and evidence agree with the generated view. These are publication constraints, not additional product goals or test cases. The concrete invocation and prerequisites for the specification and catalog validation outcomes remain unverified in the selected source.

| Requirement | Cases |
|---|---|
| SDD-I143-U4-R1 | inventory4-C01 |
| SDD-I143-U6-R1 | inventory6-C01 |
| SDD-I143-U6-R2 | inventory6-C02 |
| SDD-I143-U6-R3 | inventory6-C03, inventory6-C04 |
| SDD-I143-U6-R4 | inventory6-C01, inventory6-C02, inventory6-C03, inventory6-C04 |
| SDD-I143-U7-R1 | inventory7-C01 |
| SDD-I143-U8-R1 | inventory8-C01 |
| SDD-I143-U8-R2 | inventory8-C02 |
| SDD-I143-U8-R3 | inventory8-C03 |
| SDD-I143-U8-R4 | inventory8-C04 |

## 18. Implementation sequence

1. Publish this companion through the existing managed Action on the exact reviewed parent and verify the resulting branch before implementation; the retained execution contract requires publication and exact-branch validation first (`specs/task-execution-foundation.md`).
2. Implement the Tasks presentation using the existing domain, application, and adapter boundaries and the pinned `@vypdev/ha-ui` 0.1.0-next.2 contracts. Preserve existing task-shell behavior and use the bounded multiline reason control; consult the package declaration and lockfile in `frontend/package.json` and `pnpm-lock.yaml`. Existing presentation adoption references are `frontend/src/presentation/domus-automation-execution.ts` and `frontend/src/presentation/domus-task-overview.ts`.
3. Add current action-hint admission, refresh and revision review, reason draft retention, protected-view retirement, and transactional authority/revision checks. Keep task transition, authorization, receipt, history, and original-request recovery semantics owned by the retained contracts in `specs/household-tasks.md`, `specs/task-execution-foundation.md`, and `specs/task-assignment-interface.md`.
4. Extend the bounded task journal and original-request allowlist for `task.transition` through the recorded authorization boundary. Preserve frozen key/action/body/scope on recovery; exact replay yields one transition, history entry, and receipt, while a changed payload conflicts. Keep the prepared/uncertain request gate and compatibility with existing journal entries.
5. Deliver the start, block, and both unblock outcomes; multiline blocking reason validation/display; and refreshed admission, conflict review, unavailable-target, revocation, and direct-write behavior. Preserve keyboard access, English and Spanish content, and narrow touch usability. Keep the existing schema when implementation confirms persisted formats already cover the change.
6. Qualify the complete supported coverage: Ingress and standalone, both CPU images, and an immutable installed Edge candidate. Follow the existing CI acceptance gates, preserve configured self-hosted runner placement and full released action versions, and collect the corresponding UX, image, and installed-artifact evidence. The parent workflow is `.github/workflows/ci_check.yml`; its actual job scope must remain intact.

## 19. Definition of Done

- [ ] Every requirement is covered by an observable case and reciprocal traceability; each declared case exercises only the requirements it actually covers, including transition eligibility and authority, reason validation and retention, refreshed admission, reviewed conflict recovery, target unavailability/revocation, and transactional direct-write checks.
- [ ] Start, block, and unblock use current matching transition hints, preserve assignee identities, apply the specified target authority, and retain the existing task command and state-policy semantics.
- [ ] Blocking validates required meaningful multiline text with `validate_task_text(multiline=True, required=True)`, enforces the 1000 Unicode code point limit and existing Unicode/control rules, preserves correctable drafts, and shows the saved reason as text to permitted readers. Start and unblock clear current reason as specified while history retains prior reasons.
- [ ] Admission refreshes current session, scope, task detail, and action hints through the existing controller path. Stale hints never authorize a change. Conflicts retain proposed target and reason, show current facts, and require explicit review followed by a separate save at the reviewed revision. Unavailable targets require a deliberate new choice; authority revocation follows protected-view retirement; direct writes transactionally recheck current authority and exact revision.
- [ ] Original-request recovery preserves frozen request binding and scope, admits the existing `task.transition` action through recorded authorization, and proves exact replay, changed-payload conflict, and one-time transition/history/receipt behavior after interruption or restart. Current task facts remain distinguishable from the recovered historical result, including after activated restore.
- [ ] Existing CI acceptance gates pass with the configured self-hosted runner placement and full released action versions. Acceptance covers the Tasks journeys, applicable container jobs, Ingress and standalone, both CPU images, and an immutable installed Edge candidate. Preserve existing repository coverage thresholds and qualify complete supported coverage without exclusions or denominator reduction.
- [ ] Accessibility, keyboard use, narrow touch behavior, English and Spanish, and reason-control labels, instructions, and errors are reviewed against implemented journeys.
- [ ] The specification satisfies the required format; internal and cross-document consistency is checked; reciprocal catalog ownership, paths, and evidence agree with the generated view. These are observable publication outcomes, not generic maintainer acceptance. The installed root and frontend package declarations expose no `validate:specifications` or `generate:specifications` script; the concrete SDD validation invocation and prerequisite therefore remain unverified. A documentation check alone does not establish these outcomes.
- [ ] No readiness-blocking decision remains unresolved.

## 20. References and decisions

- Issue: https://github.com/vypdev/domus/issues/143
- Selected source revision: `50ddb2d60de4b4a53970ecdde70eb746ade38d30`.
- Retained owning contracts: `specs/household-tasks.md`, `specs/task-execution-foundation.md`, `specs/household-task-categories.md`, and `specs/task-assignment-interface.md`. This companion defines only the Tasks progress-interface delta; existing owner contracts and cases remain in force.
- UI package declaration and lock: `frontend/package.json` and `pnpm-lock.yaml`. Existing presentation references: `frontend/src/presentation/domus-automation-execution.ts` and `frontend/src/presentation/domus-task-overview.ts`.
- Existing acceptance workflow: `.github/workflows/ci_check.yml`; preserve its current gates, runner placement, and full action versions. The concrete invocation/prerequisite for SDK specification validation was not observed in the selected project declarations.
- Decisions: use the existing task transition command, current server action hints and authorization, controller refresh path, reason validator, journal, and original-request recovery boundary. Retain schema 34 only if implementation confirms current persisted formats suffice. Publish and verify the managed issue branch from the reviewed parent before contributor implementation.
- Deferred work: no change to the owning task contracts or unrelated task operations.
