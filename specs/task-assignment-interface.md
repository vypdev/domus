# Assign and release household tasks from the Tasks workspace

- Status: Draft
- Catalog capability: household-tasks

## 1. Executive summary

This companion specifies the Tasks workspace delta for authorized managers to review, replace, or release a task’s planned assignees. The workspace discovers assignment from the selected task’s current server-derived actions, loads authorized active household members, and submits canonical member identities with that task’s current revision. Save and recovery preserve the existing command’s authorization, state rules, and original-operation guarantees. The retained contracts and cases in `specs/household-tasks.md` and `specs/task-execution-foundation.md` remain authoritative; this document adds the assignment interface and its recovery behavior.

## 2. Problem, current behavior, and evidence

### 2.1 Problem

The Tasks workspace supports self-claiming, completion, and review, but task managers need a discoverable way to distribute planned work, replace assignees, or return eligible work to the shared pool. The requested change connects the existing protected assignment capability to the workspace; it does not define a new assignment contract.

### 2.2 Current behavior

The selected implementation contains task assignment and authorization boundaries, a task detail action named `assign`, an authorized roster read, and frontend task request and journal boundaries. The task presentation currently renders self-claim, completion, and review; the requested manager assignment editor is prospective. These are source observations, not evidence that this interface or the requested acceptance outcomes are implemented.

### 2.3 Evidence

`backend/src/domus/entrypoints/task_http.py` exposes the assignment endpoint. `backend/src/domus/application/task_commands.py` contains `TaskCommands.assign` and assignee validation; `backend/src/domus/application/task_authorization.py` maps `task.assign` to task-management permission. `backend/src/domus/application/task_queries.py` supplies task detail actions, and `backend/src/domus/application/household_roster.py` owns the roster query. Frontend boundaries include `frontend/src/presentation/domus-tasks.ts`, `frontend/src/application/task-controller.ts`, `frontend/src/application/task-ports.ts`, `frontend/src/adapters/task-http.ts`, and `frontend/src/adapters/task-journal.ts`. The retained contracts in `specs/household-tasks.md` and `specs/task-execution-foundation.md` govern assignment, task state, authority, revision, and operation receipts. The current assignment interface and its acceptance are proposed, not observed.

## 3. Actors, surfaces, and terminology

The household task manager enters from a selected task in the Tasks workspace and may edit only when that task’s current server-derived actions allow assignment. Household members are the available assignee choices; the visible names and current selection come from authorized member discovery. The task command remains the authority for household scope and current permission. Restricted members who are eligible to claim work continue through the established self-claim journey rather than receiving manager assignment controls.

“Planned assignees” means the task’s current assigned member identities, distinct from the actor who submits a command and from actual performers recorded under the retained task contract. “Release” means saving an empty assignee set only where the task’s current state permits it. The interface must use canonical member identities for commands and readable names for people.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

The proposed delta must let a currently authorized manager discover assignment from task detail, review existing assignees, discover authorized active household members, and save one or more canonical identities against the selected task revision. It must support replacement and state-permitted release, enforce the unique-member maximum of 32, and expose clear outcomes for loading, empty or unavailable discovery, denied access, invalid selection, conflict, uncertain response, and confirmed assignment.

If a competing revision wins, show the current task while retaining the local selection; require explicit review and a deliberate save using the refreshed revision. Recovery of a saved request must use its original request key, body, and scope. The complete English and Spanish desktop-keyboard and narrow-screen touch journeys must support accessible labels and focus, cancellation, save, retry, and understandable status feedback. Ingress and standalone acceptance must preserve the assigned task and original operation through restart and permit inspection of audit, completion, and performer behavior.

### 4.2 Non-goals

This companion does not change the task and execution contracts, their existing case identities, assignment authorization policy, task-state rules, self-claim policy, completion behavior, or performer attribution. It does not add assignment beyond the selected task’s advertised actions or broaden member discovery, household scope, or permissions.

### 4.3 Fixed product/safety invariants

Every assignment command must recheck current task-management authority and household scope at the command boundary, including revocation and member/profile exceptions. A client-visible action or selected identity is not proof of authority. Only authorized active household members may be admitted, subject to the established contract; duplicates, malformed identities, foreign members, and unsupported counts must be rejected through normal entry points. Release must obey the existing state machine, including the required assignee set for in-progress work.

A conflict must not silently overwrite another update or discard the user’s draft. A retry or recovery must identify the original operation and return its recorded result at most once; it must not mutate the frozen request’s key, body, or scope. These are additions to the interface contract, not replacements for the retained requirements in `specs/household-tasks.md` and `specs/task-execution-foundation.md`.

| Requirement | Behavior |
| --- | --- |
| SDD-I141-U1-R1 | In the Tasks workspace, a currently authorized task manager can discover the server-derived assign action, load authorized active household members, review the current assignment, and save one or more canonical member identities using the selected task revision, subject to the unique-member limit of 32 and task-state release rules. |
| SDD-I141-U1-R2 | Assignment commands enforce current task-management authority and household scope, including revocation and member/profile exceptions; eligible restricted members use the established self-claim journey. |
| SDD-I141-U1-R3 | After a competing revision, the interface shows the current task, retains the draft selection, and requires explicit review and deliberate retry with the refreshed revision; recovery preserves the original request key, body, and scope. |
| SDD-I141-U1-R4 | The interface distinguishes loading, empty member discovery, read failure, denied access, invalid selection, conflict, uncertain response, and confirmed assignment, and retains selected members when recovery is available. |
| SDD-I141-U1-R5 | The complete English and Spanish desktop-keyboard and narrow-screen touch journeys support editing, focus, labels, cancellation, save, retry, and understandable status feedback. |
| SDD-I141-U1-R6 | Ingress and standalone preserve the assigned task and original operation across restart, with inspectable audit and accepted completion and performer behavior. |

## 5. Current versus proposed product journey

The immutable owners `specs/household-tasks.md` and `specs/task-execution-foundation.md` remain authoritative for task lifecycle, assignment, authorization, revisions, receipts, and history. This companion adds the assignment-management journey to the existing Tasks workspace; it does not replace those contracts or their cases.

| Stage | Current contract | Proposed Tasks workspace journey | User effect |
|---|---|---|---|
| Open task | Task detail exposes server-derived actions; the selected task revision and current authorization govern commands. | A manager opens the selected task and sees assignment controls only when its current server-derived actions include `assign`. | The control reflects current eligibility rather than a client-side role guess. |
| Discover and review | Authorized household member reads are bounded and permission-scoped. Assignment distinguishes planned assignees from performers and the actor. | Load eligible active household members, display readable names and accessible selection labels, and show the current assignment. | The manager can review responsibility before changing it; an empty or unavailable directory is explicit. |
| Edit and save | Assignment replaces the assignee set under task-management authority and expected revision; at most 32 unique members are supported. | Select one or more canonical member identities, or clear the selection to release work where the task state permits. Save deliberately against the selected task revision using the existing request journal. | The task contract remains in force, including the required assignee set for in-progress work. |
| Resolve and observe | A stale revision does not apply a change; operation receipts identify the original request. | On conflict, show the current task while retaining the draft; require review and a deliberate save with the refreshed revision. On uncertain response, recover using the frozen original key, body, and scope. | The manager can distinguish unapplied work from a confirmed assignment and recover without creating a second operation. |

Flow: open task -> discover and review members -> edit selection -> save at current revision -> confirm, review conflict, or recover the original operation. The selected task and member identities remain within current household scope throughout.

## 6. Functional behavior and state model

### 6.1 Normal path and alternatives

1. The Tasks workspace reads task detail and uses its current server-derived `assign` action to offer assignment management. The command boundary independently checks current task-management authority and household scope; visibility is not authorization.
2. The workspace loads authorized active household members and presents their names with the task’s current selected members. Loading, successful empty discovery, and read failure have distinct feedback. Inactive, outdated, or unauthorized options cannot be admitted as valid current choices.
3. The manager selects up to 32 unique canonical member identities and saves against the displayed task revision. A successful response reports the confirmed assignment; refreshing task detail shows the committed planned assignees. Replacing the set is supported. Clearing it releases supported task states to the shared pool; an in-progress task must retain its contractually required assignee set.
4. A restricted member eligible to self-claim follows the established self-claim journey. The editor and direct command do not grant reassignment authority to a restricted member or treat a selected identity as proof of authority.

Malformed, duplicate, over-limit, inactive, or foreign identities produce actionable validation or denial while preserving the editable draft when safe. Current authorization, membership/profile exceptions, and scope are checked at command time, including after revocation. These rules extend the retained assignment and permission contracts in `specs/household-tasks.md` and `specs/task-execution-foundation.md`.

### 6.2 State and recovery

| Interface state | Meaning and next action | Retained facts |
|---|---|---|
| Loading members/task | Current authorized reads are pending; wait for results. | Existing draft selection. |
| Empty member discovery | Read succeeded with no eligible active options; explain that assignment cannot proceed and allow refresh or exit. | Existing task context and draft where applicable. |
| Read failure | Discovery or task read failed; offer an explicit retry when safe. Do not present failure as an empty list. | Existing draft selection. |
| Denied | Current authority or household scope does not permit the read or command; do not expose protected member/task details. Eligible restricted members may use self-claim where offered. | Only information already authorized for display. |
| Invalid selection | The submitted selection violates identity, uniqueness, count, availability, or task-state rules; correct the selection. | Draft selection and current task context. |
| Conflict | Another change won at the selected revision; show the current task, retain the draft, and require deliberate review and save using the refreshed revision. Never blindly retry a changed assignment. | Refreshed task/revision and editable draft. |
| Uncertain response | The client cannot determine whether the command completed; recover or retry the exact original request using its frozen key, body, and scope. | Original operation identity and payload. |
| Confirmed assignment | The command receipt confirms the recorded result; refresh may verify the current task projection. | Receipt and committed assignment facts. |

A lost response recovered under the same frozen operation returns the original recorded assignment once. A changed payload under the same key is not a retry; a genuinely new deliberate command requires a new operation identity. Existing receipt, revision, and history semantics remain owned by the immutable task contracts. The concrete observable journeys include replacement/release and the in-progress constraint, authorization and denial, authorized member discovery, conflict review, frozen-request recovery, and validation boundaries.

## 7. User-facing configuration

No user-facing configuration is introduced. The assignment editor uses the existing task-management authority, household scope, task state machine, expected revision, and unique-member limit of 32. These are fixed contract constraints, not preferences a household can weaken. The selected task and authorized discovery determine the available choices; the current assignment is displayed for review. Eligible restricted members continue to use the established self-claim policy and journey described by `specs/task-execution-foundation.md`. No new persistence or migration setting is required by this interface delta.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

The assignment interface extends existing task boundaries described in `specs/household-tasks.md` and `specs/task-execution-foundation.md`; it must not create a parallel authorization or task-state implementation.

| Boundary | Responsibility for this delta | Must not own |
|---|---|---|
| Domain policy | Existing task policy defines valid assignee sets, release eligibility, in-progress constraints, revisions, and task transitions. | UI selection state, provider DTOs, or presentation decisions. |
| Application | Coordinate authorized member discovery and assignment command; return semantic outcomes for success, denial, validation, conflict, and recovery. | Framework rendering or client-side authority decisions. |
| Semantic ports | Express task detail/action, authorized member discovery, assignment, and original-operation recovery in domain terms. | Provider-specific response shapes as product policy. |
| Adapters and infrastructure | Map the existing task and roster interfaces, HTTP results, and request-journal records to semantic contracts; preserve operation identity and map errors accurately. | Duplicated task authorization/state rules or claims that a request succeeded without its result. |
| Entrypoints and composition | Adapt authenticated workspace/API input and wire the existing services while preserving the established trust boundary. | Duplicated orchestration or trusting client-supplied member IDs as authority. |
| Presentation | Render task action availability, member names and labels, current/draft selection, status, and recovery choices accessibly in English and Spanish. | Authorization, mutation policy, revision resolution, or direct persistence. |

Dependency direction: Tasks workspace presentation -> application use cases -> domain policy and semantic ports <- task/member adapters; composition supplies adapters to the existing entrypoints. View state may retain a draft selection, while the server remains authoritative for current task, members, permission, revision, and command outcome.

### 8.2 Contracts, state, and trust boundaries

The assignment command accepts canonical member identities, the selected expected task revision, and the existing operation identity/scope contract. Authorized member discovery supplies names and eligibility data; the client must not infer eligibility from cached profiles or treat a supplied identity as a grant. The command rechecks current task-management authority, household scope, member/profile exceptions, and revision at commit. The existing task request journal freezes key, body, and scope for recovery. Conflict refresh changes the revision used by a later deliberate command, not the original operation payload. Receipts and task history remain the durable evidence of committed assignment and actor.

### 8.3 Executable constraints

Architecture and acceptance evidence must demonstrate that UI action visibility cannot bypass command authorization; assignment and release use the existing revisioned command boundary; member reads remain permission-scoped; retries preserve the original request; and provider errors map to distinct user-observable states. The repository standard requires executable dependency/contract checks, but the concrete invocation and prerequisites for specification validation are unverified in the selected project; do not treat an example command as evidence that this interface or its boundaries have been checked.

## 9. UI/UX and content contract

The Tasks workspace exposes assignment editing only when the selected task’s current server-derived actions include `assign`. Show the current assignees by readable name, load available choices through authorized household member discovery, and submit canonical member identities with the selected task revision. Allow up to 32 unique members. Offer release to the shared pool only when the task state permits an empty assignee set; preserve the in-progress assignee constraint. Replacing an assignment or releasing work must be a deliberate save. The retained task state and authorization contracts remain in `specs/household-tasks.md` and `specs/task-execution-foundation.md`.

```text
Assign task: Water the plants
Current assignees: Mina
Select household members (up to 32)
[x] Mina
[ ] Luis

[Cancel]  [Save assignment]
```

Provide localized labels, instructions, validation, and status feedback in English and Spanish, following the existing fallback conventions. The editor and member list must work with keyboard and touch at desktop and narrow-screen sizes, with visible logical focus, accessible names, and state conveyed in text. Cancellation returns to task detail without saving. After a save, show whether the assignment was confirmed and who is responsible; do not imply success while the result is uncertain. The existing task presentation contract is in `specs/task-execution-foundation.md`.

## 10. Failure, recovery, and cleanup

Show distinct loading, empty member list, read failure, denied access, invalid selection, conflict, uncertain response, and confirmed assignment states. Empty discovery is not a read failure. Explain errors in impact, cause, next action, then retained state order. Keep the draft selection when recovery is possible.

If the task revision changed, show the current task and its assignment, retain the draft, and require the manager to review and deliberately save again with the refreshed revision. Do not silently rebase or automatically resubmit. For a lost response, recover or retry the original operation using its frozen request key, body, and scope; return the original recorded result once. A genuinely changed request requires a new operation. These rules extend the revision and receipt behavior in `specs/task-execution-foundation.md`.

## 11. Security, permissions, and privacy

The editor is a presentation affordance, not an authority boundary. Recheck current task-management authority, household scope, membership and applicable member/profile exceptions at the command boundary, including revocation between display and save. A selected member identity conveys no authority. Denied, restricted, revoked, or foreign-household attempts must not change the assignment or disclose unauthorized member data. Eligible restricted members use the established self-claim journey. Use authorized member discovery for options and current selections; reject inactive, outdated, malformed, duplicate, over-limit, or foreign identities through normal entry points. Preserve the task execution authorization and privacy contract in `specs/task-execution-foundation.md`.

## 12. Observability and operational UX

Give the manager a clear status for discovery and save, including whether action is required and whether responsibility has changed. On success, show the confirmed assignee names and refreshed task state. On conflict or uncertain response, state what is known, what remains unresolved, and the recovery action. Operational evidence may distinguish denial, validation failure, revision conflict, and unavailable discovery, using existing sanitized handling. Do not expose credentials, household identifiers, unrestricted payloads, or unnecessary member details in diagnostics. No new external telemetry or notification behavior is established by this delta; concrete logging or metric hooks remain unverified in the selected source.

## 13. Compatibility, migration, rollout, and rollback

This companion adds assignment management to the existing Tasks workspace and relies on the retained task command, revision, authorization, and operation-receipt contracts in `specs/household-tasks.md` and `specs/task-execution-foundation.md`. Preserve existing task states, self-claim and completion behavior, and in-flight operation recovery. The required behavior applies to ingress and standalone: after restart, the assigned task and original operation remain recoverable, with inspectable audit and the accepted completion and performer behavior. Determine whether migration is needed from implementation evidence; no migration or rollout mechanism is established by this draft. Validate the English and Spanish journeys, both deployment targets, restart and restore behavior, and installed Edge acceptance as product outcomes. The concrete invocation and prerequisites for these checks remain unverified in the selected source.

## 14. Testing strategy and numeric budget

The minimum budget is nine distinct companion cases, one for each defined acceptance scenario. This is a floor, not evidence that tests have run or that the behavior is complete. Allocate coverage across authorized assignment and member discovery; task-state and member-identity validation; revision conflict and original-operation recovery; English/Spanish keyboard and touch usability; and persistence, audit, and completion/performer behavior in both ingress and standalone compositions. Exercise normal entry points and direct commands, including current authority and household scope. Use deterministic responses and controlled restart/recovery conditions; do not count repeated runs of the same behavior as distinct cases.

The retained contracts remain authoritative for task-state, assignment, authorization, and execution behavior: `specs/household-tasks.md` (including household-tasks-R3) and `specs/task-execution-foundation.md` (including TEF-03 and the assignment and role-default sections). Their existing cases remain references and are not redefined or credited to this companion. The selected source shows the assignment route in `backend/src/domus/entrypoints/task_http.py`; `TaskCommands.assign` is declared in `backend/src/domus/application/task_commands.py`. Task action derivation is in `backend/src/domus/application/task_queries.py`. These are source facts, not acceptance evidence for the proposed interface.

The repository standard names `pnpm run validate:specifications` in `specs/README.md`, but this draft has not verified its execution prerequisites or the referenced validator definition. No concrete invocation for complete SDK specification/catalog consistency is established here. Record validation as an outcome: authored specification requirements are checked against the required format and internal/cross-document consistency, without representing a command declaration as an executed or passing check.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| assignment | 2 | Observable scenarios in the case inventory. |
| authorization | 1 | Observable scenarios in the case inventory. |
| member discovery | 1 | Observable scenarios in the case inventory. |
| conflict | 1 | Observable scenarios in the case inventory. |
| recovery | 1 | Observable scenarios in the case inventory. |
| validation | 1 | Observable scenarios in the case inventory. |
| usability | 1 | Observable scenarios in the case inventory. |
| persistence | 1 | Observable scenarios in the case inventory. |
| Total | 9 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| task-assignment-interface-C01 | assignment | SDD-I141-U1-R1 | An authorized task manager selects one or multiple active members and observes the committed planned assignment after refresh. |
| task-assignment-interface-C02 | assignment | SDD-I141-U1-R1 | The manager replaces an existing assignment and releases a supported task to the shared pool; an in-progress task enforces its required assignee set. |
| task-assignment-interface-C03 | authorization | SDD-I141-U1-R2 | Current authority and scope govern the editor and direct command. Restricted, denied, revoked, and foreign-household attempts receive the appropriate denial. |
| task-assignment-interface-C04 | member discovery | SDD-I141-U1-R1, SDD-I141-U1-R4 | Member options and current selections use authorized discovery. Empty, unavailable, inactive, and outdated options have explicit recovery and admission outcomes. |
| task-assignment-interface-C05 | conflict | SDD-I141-U1-R3, SDD-I141-U1-R4 | A competing revision produces a conflict. Reviewing the current task retains the draft selection and requires a deliberate save using the refreshed revision. |
| task-assignment-interface-C06 | recovery | SDD-I141-U1-R3, SDD-I141-U1-R4 | A lost response is resolved through the same frozen key and body. Retrying or recovering returns the original recorded assignment once. |
| task-assignment-interface-C07 | validation | SDD-I141-U1-R1, SDD-I141-U1-R4 | Supported member-count boundaries and malformed, duplicate, or foreign identities are validated through the normal entry points. |
| task-assignment-interface-C08 | usability | SDD-I141-U1-R5 | English keyboard and Spanish mobile touch journeys cover editing, cancellation, save, conflict review, and retry with understandable focus and feedback. |
| task-assignment-interface-C09 | persistence | SDD-I141-U1-R6 | Ingress and standalone retain the assigned task and original operation after restart, with an inspectable audit and the accepted completion and performer behavior. |

## 15. Documentation and discoverability

Document the Tasks workspace assignment journey, including how managers discover the server-derived action, choose and review members, release work when allowed, and recover from conflicts or uncertain responses. Explain the visible states and the meaning of a confirmed assignment, and provide localized English and Spanish guidance consistent with the interface. Keep task rules and authority in the retained owners, `specs/household-tasks.md` and `specs/task-execution-foundation.md`; this companion documents their interface and recovery delta rather than restating those contracts. The existing user guide is `docs/user-guide.md`.

The selected project declares `@vypdev/ha-ui` version `0.1.0-next.2` in `frontend/package.json`; the interface should use the published controls specified by the issue while preserving the existing frontend task boundaries. The request journal boundary is declared as `TaskJournalPort` in `frontend/src/application/task-ports.ts`, with `TaskSessionJournal` in `frontend/src/adapters/task-journal.ts`. Concrete verification of the package's rendered behavior and a complete SDK consistency invocation remain unverified.

| Path | Change |
| --- | --- |
| specs/task-assignment-interface.md | create |

[specs/task-assignment-interface.md](task-assignment-interface.md)

## 16. Acceptance scenarios

These are future observable acceptance scenarios; none is represented as implemented, executed, or passed.

1. In the Tasks workspace, a currently authorized task manager sees the assignment control only when the selected task’s server-derived actions allow it, discovers authorized active household members, and saves one or multiple canonical identities at the selected revision. After refresh, the planned assignment is visible. Replacing an assignment and releasing supported work behave according to the retained task-state rules; an in-progress task preserves its required assignee set. (task-assignment-interface-C01, task-assignment-interface-C02)
2. Current task-management authority and household scope govern both editor and command. Restricted, denied, revoked, and foreign-household attempts are denied appropriately, while eligible restricted members can use the established self-claim journey. Member discovery distinguishes empty, unavailable, inactive, and outdated options and gives an explicit recovery and admission outcome. (task-assignment-interface-C03, task-assignment-interface-C04)
3. When a competing revision wins, the interface identifies the conflict and shows the current task. It retains the draft selection, requires review, and only retries after deliberate action using the refreshed revision. If a response is lost, recovery uses the original frozen request key and body and returns the original recorded assignment once. (task-assignment-interface-C05, task-assignment-interface-C06)
4. Normal entry points reject unsupported member counts, malformed or duplicate identities, and foreign identities with understandable validation. Loading, empty discovery, read failure, denial, invalid selection, conflict, uncertain response, and confirmed assignment are distinguishable; selected members remain available when recovery permits. (task-assignment-interface-C04, task-assignment-interface-C06, task-assignment-interface-C07)
5. The complete English desktop keyboard journey and Spanish narrow-screen touch journey support editing, labels, focus, cancellation, save, conflict review, retry, and understandable status feedback. (task-assignment-interface-C08)
6. In both ingress and standalone, restart retains the assigned task and original operation; the audit can be inspected, and accepted completion and performer behavior remains intact under the retained contracts. (task-assignment-interface-C09)

The companion scenarios refine the existing task journey; they do not change the retained owners’ state machine, assignment semantics, or role defaults.

## 17. Requirements traceability

The host-maintained traceability inventory must map each requirement to only the cases that exercise it, reciprocally with the case definitions. Assignment discovery, authorized member selection, save, revision, member limit, and state-permitted release map to task-assignment-interface-C01, task-assignment-interface-C02, task-assignment-interface-C04, and task-assignment-interface-C07. Current authority, household scope, revocation, restricted-member exceptions, and self-claim map to task-assignment-interface-C03. Conflict review and deliberate refreshed-revision retry map to task-assignment-interface-C05; frozen-key/body recovery maps to task-assignment-interface-C06. Distinct interface states and retained selections map to task-assignment-interface-C04, task-assignment-interface-C05, task-assignment-interface-C06, and task-assignment-interface-C07. Localization, input mode, focus, labels, cancellation, save, and retry map to task-assignment-interface-C08. Restart, audit, and retained completion/performer behavior map to task-assignment-interface-C09. Preserve all nine case identities exactly; existing owner case IDs are references, not new definitions.

Publication acceptance must make three outcomes observable: the specification satisfies the required format; internal and cross-document consistency is checked; and reciprocal catalog ownership, paths, and evidence agree with the generated view. Structural counts and reciprocal mappings establish inventory consistency only; they do not establish semantic completeness or executed acceptance. The selected tree declares `pnpm run validate:specifications` in `specs/README.md`, but the invocation prerequisites and validator definition were not inspected, so its availability and scope remain unverified. No specific command is asserted as satisfying these publication outcomes.

| Requirement | Cases |
|---|---|
| SDD-I141-U1-R1 | task-assignment-interface-C01, task-assignment-interface-C02, task-assignment-interface-C04, task-assignment-interface-C07 |
| SDD-I141-U1-R2 | task-assignment-interface-C03 |
| SDD-I141-U1-R3 | task-assignment-interface-C05, task-assignment-interface-C06 |
| SDD-I141-U1-R4 | task-assignment-interface-C04, task-assignment-interface-C05, task-assignment-interface-C06, task-assignment-interface-C07 |
| SDD-I141-U1-R5 | task-assignment-interface-C08 |
| SDD-I141-U1-R6 | task-assignment-interface-C09 |

## 18. Implementation sequence

Implement the Tasks workspace delta against the retained contracts in `specs/household-tasks.md` and `specs/task-execution-foundation.md`; leave `specs/household-task-categories.md` unchanged. Connect the server-derived assignment action and authorized active-member discovery to an editor that shows readable current assignees, accepts canonical member identities, and submits the selected task revision. Enforce current task-management authority and household scope at the command boundary, the unique-member limit of 32, and the existing state rules for replacement and release, including the in-progress assignee constraint. Preserve the eligible restricted-member self-claim journey.

Implement conflict review so the current task is shown while the draft selection remains available; require a deliberate save with the refreshed revision. Freeze the original request key, body, and scope for uncertain-response recovery. Present distinct loading, empty, read-failure, denied, invalid-selection, conflict, uncertain, and confirmed states, retaining selections when recovery is available. Complete the English and Spanish keyboard and narrow-screen touch journeys, then qualify authorized assignment and release, authority and scope denials, member discovery outcomes, conflict review, original-operation recovery, input boundaries, localization and accessibility, and persistence across restart in ingress and standalone. Determine migration needs from implementation evidence and verify audit, completion, and performer behavior against the retained task contract.

## 19. Definition of Done

Done when all nine supplied acceptance cases preserve their declared identities and concrete observable assertions, and every requirement maps only to cases that exercise it. Evidence must establish that authorized managers can assign one or more active members, replace assignments, and release supported tasks; current authority and household scope govern both the editor and direct command; member discovery and its empty, unavailable, inactive, and outdated outcomes are explicit; conflicts retain the draft and require reviewed retry at the refreshed revision; and uncertain responses recover the original recorded assignment once using the frozen request. Verify supported member-count boundaries and rejection of malformed, duplicate, or foreign identities through normal entry points. Verify understandable English keyboard and Spanish mobile touch flows, including focus, labels, cancellation, save, conflict review, and retry. Verify ingress and standalone restart persistence, inspectable audit, and the retained completion and performer behavior. These are acceptance outcomes, not claims that implementation or tests have run.

The specification satisfies the required format; internal and cross-document consistency is checked; reciprocal catalog ownership, paths, and evidence agree with the generated view. Preserve these three publication outcomes as explicit acceptance gates. The selected source documents the specification standard in `specs/README.md`; the concrete invocation and prerequisites for these publication checks remain unverified. Required product validation, coverage, and deployment evidence must be reported with their actual scope; a declaration or structural count alone is not executed acceptance or semantic completeness.

## 20. References and decisions

Issue: https://github.com/vypdev/domus/issues/141. This is a bounded companion delta for the household-tasks capability. Existing contracts and cases remain owned by the immutable `specs/household-tasks.md` and `specs/task-execution-foundation.md`; `specs/household-task-categories.md` remains unchanged. The selected source revision is `6c7428dd7101a375802b67c3c7e8c2513b2c2053`. The repository standard is `specs/README.md`. The issue describes existing assignment, authorization, revision, receipt, and member-discovery entry points; implementation details and verification outcomes must be confirmed against the selected project during implementation. No verification command or passing result is asserted here.
