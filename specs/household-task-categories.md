# Persist household task categories and use them in the protected calendar

- Status: Draft
- Catalog capability: household-tasks

## 1. Executive summary

This companion completes the retained household-task contract by storing optional, exact household category references separately from tags, exposing category selection on ordinary and scheduled task journeys, and filtering the protected calendar by the actual category. Legacy work remains unclassified. Current authorization, household scope, operation recovery, and historical task facts remain intact. The existing owners and their cases remain authoritative; this document adds only the category delta.

## 2. Problem, current behavior, and evidence

The existing task owner allows an optional category on a task definition and distinguishes task facts from tags; the recurrence foundation likewise requires an exact active household category and explicitly rejects treating tags as category aliases. In the selected source, task values validate tags as bounded text, and the calendar query projects those tags. The calendar presentation currently offers a free-text “category” filter, and the calendar guide describes it as a category tag. These are current implementation observations, not the proposed category contract. See `specs/household-tasks.md`, `specs/recurrence-execution-foundation.md`, `backend/src/domus/domain/task_values.py`, `backend/src/domus/application/calendar_queries.py`, `frontend/src/presentation/domus-calendar.ts`, and `docs/tasks/calendar.md`.

The selected SQLite implementation declares schema version 14. The selected `tests/fixtures/sqlite/v14.sql` has SHA-256 `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`; it is the prospective migration input to preserve byte-for-byte, with its real pre-category tasks, tags, snapshots, and original receipts verified by the migration acceptance work. The fixture and current schema declaration establish the baseline; they do not establish that category persistence or migration has been implemented. The task and recurrence owners remain the sources for their broader behavior and retained cases.

## 3. Actors, surfaces, and terminology

Task administrators manage the household’s category catalog. Authorized task authors may leave a task unclassified or select an active category while creating ordinary or scheduled work. Authorized calendar readers may filter by an active category within their current household. The task and protected calendar browser surfaces expose these actions; existing task and recurrence contracts continue to govern their other behavior.

A category is a household-owned, revisioned entity with an inert label and active or archived state. A task’s category is an optional exact reference, separate from its tags. “Unclassified” means no category reference; it is not a generated category or a tag-derived value. Issued task facts retain their historical category identity and captured label when catalog entries are renamed or archived.

## 4. Goals, non-goals, and fixed invariants

The bounded goals are to preserve schema-14 task content, tags, snapshots, receipts, and operations while migrating legacy work as unclassified; let only currently authorized task administrators create, rename, and archive categories with revision and original-operation protection; let task authors select an active category for ordinary and scheduled tasks and let protected calendar readers filter by the exact category with entries and both counts computed from the same authorized predicate; and preserve history and recovery through archive, stale commands, rollback, and restore while presenting localized task and calendar controls. The inventory’s four requirements and seven concrete cases define the refinements and their verification; these outcomes are prospective, not claims of completed implementation.

This increment does not replace or rewrite `specs/household-tasks.md` or `specs/task-execution-foundation.md`, and does not change their retained contracts or cases. It does not introduce stock categories, rewards, gateway changes, publication behavior, or deployment work. Tags remain independent free-form task data and never establish category identity. Omitted category assignment remains valid; title-only task creation remains supported. Foreign or inactive category assignment and filtering must not disclose other household data or alter a rejected task draft. Current authorization and scope apply on every command and read; retries recover only the original operation under current permission. Migration failure leaves original database bytes and schema intact; rollback and restore preserve business state and historical facts.

| Requirement | Behavior |
| --- | --- |
| task-categories-R1 | Preserve schema-14 tasks, tags, snapshots and original operations. Legacy work remains unclassified after migration. |
| task-categories-R2 | Current authorized task administrators manage exact active categories with revision and original-operation protection. Reject foreign or inactive category assignment. |
| task-categories-R3 | Task authors can select a category on ordinary and scheduled task journeys. Calendar queries filter on the actual category and calculate both counts over the same authorized predicate. |
| task-categories-R4 | Preserve history, scope and recovery across archive, stale commands, rollback and restore. Present localized task and calendar controls. |

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User/operator effect |
|---|---|---|---|
| Manage categories | Task specifications require configurable categories, but category administration is not part of the selected implementation. | A currently authorized task administrator creates, renames, or archives a household category with revision and original-operation protection. | The household has a controlled list of exact, active category identities. |
| Author work | Task content has tags; schema-14 work has no persisted category reference. | An author may leave a task unclassified or select an active category for ordinary, fixed, and completion-relative work. | Category identity is stored separately from tags; existing tasks remain unclassified. |
| Read the calendar | The protected calendar’s category predicate matches free-form tags in `backend/src/domus/infrastructure/sqlite_calendar.py`. | A reader filters by an exact active category within the authorized household; entries and both counts use the same combined predicate. | The filtered calendar reflects category references without exposing foreign records. |
| Preserve history | Existing owners require task snapshots, history, and original receipts to remain meaningful. | Rename and archive preserve already-issued task snapshots and evidence; migration and compatible rollback preserve business state. | Current choices change without rewriting historical facts.

## 6. Functional behavior and state model

A category is a household-owned entity with an exact identity, an inert label of 1–80 characters, a revision, and active or archived state. Create, rename, and archive require current task-administrator authority, expected revision, and original-operation handling. Stale revisions fail without a new effect; a retry after a lost response recovers the same operation subject to current permission.

Task classification is optional and separate from tags. Omitted classification means unclassified; it must not be inferred from existing tags. Ordinary, fixed, and completion-relative task creation may select an active category in the current household. Foreign or archived identities are rejected while retaining the task draft and existing records. Rename or archive does not rewrite category identity or captured label in issued task snapshots or original evidence.

Protected calendar filtering accepts an exact active category identity scoped to the current household and session. Combine it with timing, state, priority, and member filters in one authorized predicate; the returned entries, event count, and distinct occurrence count must agree across pages. A foreign or archived category cannot be selected or used to disclose entries. Tags remain independent and are never treated as category identity.

Migration uses the immutable schema-14 input `tests/fixtures/sqlite/v14.sql` (observed SHA-256 `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`). Preserve its bytes, existing tasks, tags, snapshots, and original receipts; migrated legacy work is unclassified. Migration is atomic: injected failure retains the exact original bytes and schema. Snapshot inspection checks exact category references and current schema. Compatible rollback retains original business state; the previous image refuses the new schema safely. These are proposed acceptance conditions, not evidence that implementation or checks have run.

## 7. User-facing configuration

Task forms retain the title-only path and add an optional category selector with an explicit unclassified choice. Show only active choices available to the current authorized household; selecting a foreign or archived category is invalid and leaves the draft intact. Ordinary, fixed, and completion-relative creation use the same optional classification behavior. Tags remain a separate field.

Only a currently authorized task administrator sees category create, rename, and archive controls. Require a bounded inert label (1–80 characters), current revision, and original-operation identity for changes. Show actionable validation and conflict results without discarding entered task content. Category controls and the calendar filter must have localized English and Spanish labels, accessible names and errors, and preserve draft state on invalid selection. The protected calendar offers active categories and reports the authorized filtered entries and both counts.

## 8. Clean Architecture design

Domain policy owns typed category identity, bounded inert labels, active/archive state, and the distinction between category references and tags. Application use cases own current authorization, household scoping, revision checks, task assignment validation, original-operation recovery, and the shared calendar query predicate. Semantic ports separate these decisions from persistence.

SQLite infrastructure owns the atomic schema transition, durable category records, task classification, snapshot preservation, and category-aware calendar query. Entrypoints adapt bounded inputs and safe validation, conflict, and receipt results; they do not duplicate authorization or orchestration. Frontend domain and presentation code own selector and filter state, draft preservation, accessible localized rendering, and display of authorized results. Both browser compositions must exercise the real controls.

Keep the current task-read, task-write, and protected task-configuration grants; bind category IDs, revisions, filters, pagination, and receipts to the current household and session. Verify migration, rollback, stale and retried commands, snapshot behavior, and combined calendar predicates against actual data. The selected repository declares `pnpm run validate:specifications` in `specs/README.md` for specification changes, but its execution directory, package-manager availability, and referenced validation definition have not been verified here; declaration is not execution or proof of these product outcomes.

## 9. UI/UX and content contract

Present category controls in both browser compositions using the project’s English and Spanish localization behavior. Task forms keep category optional, offer an explicit unclassified choice, and display only active categories the current household may use. Keep category labels inert and distinguish them from free-form tags. On an invalid or newly archived selection, identify the field, explain that the choice is unavailable, and retain the rest of the draft; title-only task creation remains available. The protected calendar’s category filter uses category identity, composes with timing, state, priority, and member filters, and presents event count separately from distinct occurrence count. Verify keyboard access, accessible names and focus, non-color status cues, and localized browser behavior for both compositions. These are additions to the existing task and recurrence journeys in `specs/household-tasks.md` and `specs/task-execution-foundation.md`.

## 10. Failure, recovery, and cleanup

Reject foreign or archived category references and stale category edits before they create new effects; report a bounded field error or conflict and preserve the submitted task draft and existing records. When a command response is lost, recovery uses the same operation identity and returns its original receipt only after current permission is checked; a retry must not create another category or task effect. Category rename or archive must not rewrite issued task snapshots or original evidence. Migration failure must leave the schema version and original database bytes unchanged. A compatible rollback preserves business state, while an image that cannot read the resulting schema must refuse it safely. Verify these outcomes with the migration, stale-command, receipt-recovery, and history scenarios; do not treat a declaration or command invocation as executed evidence.

## 11. Security, permissions, and privacy

Apply current task-read, task-write, and protected task-configuration authorization on the server for category administration, assignment, and calendar queries. Bind category identity, revision, household, session, filters, range, and pagination to the authenticated current context; recheck authority at the mutation boundary and before disclosing an original receipt. A selected member or category ID is not proof of identity or authority. Foreign and archived categories must not be assignable or exposed through a protected calendar query. Keep category labels inert, validate bounded input, and redact credentials and unnecessary personal data from logs, traces, exports, and browser artifacts, consistent with `specs/household-tasks.md`.

## 12. Observability and operational UX

Return bounded, actionable field errors for invalid selections, conflicts for stale revisions, and the original operation receipt for an authorized retry. Explain the retained draft or committed state and a safe next action without exposing foreign category or task data. Authorized readers may see historical category snapshots on issued work after rename or archive; current active choices remain distinct from those snapshots. Operational evidence should distinguish denied, invalid, conflict, unavailable, and completed outcomes without credentials or unrestricted request payloads. Acceptance requires the observable task and calendar states and matching authorized entries, event counts, and distinct occurrence counts for the same query predicate.

## 13. Compatibility, migration, rollout, and rollback

Migrate the genuine pre-category SQLite schema-14 input atomically to the next schema. Preserve existing tasks, tags, snapshots, original operations and receipts; migrated legacy work remains unclassified, and tags are never reinterpreted as categories. The selected source contains `tests/fixtures/sqlite/v14.sql`; its observed SHA-256 is `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`. Keep that fixture byte-for-byte as migration input. Verify migration by inspecting exact category references and current schema, injected-failure preservation of original bytes and version, and compatible rollback with the prior image’s safe refusal of the new schema. Restore must use a compatible data and image pair. Existing task and recurrence owner contracts and cases remain in force. The concrete project verification invocation and prerequisite remain unverified here; acceptance is the specified observable migration, rollback, and restore outcomes, not an assumed script.

## 14. Testing strategy and numeric budget

The minimum is seven distinct category cases, one for each supplied scenario; executions that satisfy several scenarios remain shared evidence and do not change the count. Cover schema-14 preservation and atomic failure; household authorization, active-category validation, revision conflicts, and original-operation recovery; ordinary and scheduled task classification with historical snapshots; protected calendar filtering with consistent entries and both counts; localized browser controls and draft retention; and snapshot inspection, compatible rollback, and safe refusal by the previous image. Exercise the real SQLite migration input at `tests/fixtures/sqlite/v14.sql`, both browser compositions, and the actual current images. The fixture’s observed SHA-256 is `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`; it is a selected-tree file, while the issue’s source-merge identity is not independently established by this tree. Preserve this fixture byte-for-byte.

Require complete supported repository and per-file coverage, including statements and branches for changed backend modules; architecture and adapter contract checks; deterministic IDs and time; real SQLite behavior; and semantic assertions for authorization, pagination, localization, recovery, and retained history. These are acceptance outcomes, not claims of execution. The selected package declarations establish pnpm 10.34.0 with Node `>=24.20.0 <25`, and uv/Python `>=3.14,<3.15`; they do not establish a category-specific verification invocation or that any check has passed. The concrete complete-coverage and product-validation invocations and prerequisites remain unverified.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Migration | 2 | Observable scenarios in the case inventory. |
| Authorization | 2 | Observable scenarios in the case inventory. |
| Application | 2 | Observable scenarios in the case inventory. |
| Browser | 1 | Observable scenarios in the case inventory. |
| Total | 7 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| task-categories-C01 | Migration | task-categories-R1 | Genuine schema-14 tasks, tags and original receipts survive migration as unclassified; injected failure leaves exact original bytes and schema. |
| task-categories-C02 | Authorization | task-categories-R2 | A foreign or archived category cannot be assigned or selected in a protected calendar query. The task draft and original records remain intact. |
| task-categories-C03 | Authorization | task-categories-R2, task-categories-R4 | Only a current task administrator can create, rename or archive. A stale revision fails and a lost response recovers the same operation. |
| task-categories-C04 | Application | task-categories-R1, task-categories-R3, task-categories-R4 | Ordinary, fixed and relative tasks carry the correct optional classification. Rename or archive preserves already issued task snapshots and original evidence. |
| task-categories-C05 | Application | task-categories-R3 | Combined category, timing, state, priority and member filters produce the same authorized entries, event count and distinct occurrence count on every page. |
| task-categories-C06 | Browser | task-categories-R3, task-categories-R4 | Both browser compositions render the real localized category selector, preserve the draft on invalid selection and display the authorized filtered calendar. |
| task-categories-C07 | Migration | task-categories-R1, task-categories-R4 | Snapshot inspection verifies exact category references and current schema. A compatible rollback retains the original business state and the previous image refuses the new schema safely. |

## 15. Documentation and discoverability

Document category administration, exact active-category selection and the unclassified option, ordinary and scheduled task assignment, protected calendar filtering, localized controls, migration compatibility, rollback, and troubleshooting. Keep tags distinct from category identity and explain that legacy tasks remain unclassified. Update the user-facing calendar guidance in `docs/tasks/calendar.md` and cross-reference the retained contracts in `specs/household-tasks.md`, `specs/task-execution-foundation.md`, `specs/recurrence-execution-foundation.md`, and `specs/recurrence-lifecycle-calendar.md`. The supplied inventory declares 24 prospective path operations; its create and update rows are proposed work, not evidence that those files or behaviors exist. The schema-14 fixture is verified at `tests/fixtures/sqlite/v14.sql`.

Validate documentation links and navigation, and ensure examples agree with the implemented API, fixtures, and English and Spanish UI. The selected root package declares pnpm scripts for general tests, frontend tests, and TypeScript checks, while the Python project declares `domus-check` at `domus_tooling.cli:main`; these declarations do not establish specification-format, internal/cross-document consistency, reciprocal catalog ownership, or generated-view validation. Concrete invocations and prerequisites for those publication outcomes remain unverified.

| Path | Change |
| --- | --- |
| specs/household-task-categories.md | create |
| specs/household-tasks.md | reference |
| specs/task-execution-foundation.md | reference |
| specs/recurrence-execution-foundation.md | reference |
| specs/recurrence-lifecycle-calendar.md | reference |
| backend/src/domus/domain/task_categories.py | create |
| backend/src/domus/domain/task_values.py | update |
| backend/src/domus/application/task_category_commands.py | create |
| backend/src/domus/application/ports.py | update |
| backend/src/domus/application/task_creation.py | update |
| backend/src/domus/application/calendar_queries.py | update |
| backend/src/domus/infrastructure/sqlite.py | update |
| backend/src/domus/infrastructure/sqlite_task_categories.py | create |
| backend/src/domus/infrastructure/sqlite_task_records.py | update |
| backend/src/domus/infrastructure/sqlite_calendar.py | update |
| backend/src/domus/entrypoints/task_category_http.py | create |
| backend/src/domus/entrypoints/task_http.py | update |
| backend/src/domus/entrypoints/task_dto.py | update |
| frontend/src/domain/tasks.ts | update |
| frontend/src/domain/calendar.ts | update |
| frontend/src/presentation/domus-tasks.ts | update |
| frontend/src/presentation/domus-calendar.ts | update |
| tests/backend/test_task_categories.py | create |
| docs/tasks/calendar.md | update |
| tests/fixtures/sqlite/v14.sql | reference |

[specs/household-task-categories.md](household-task-categories.md) · [specs/household-tasks.md](household-tasks.md) · [specs/task-execution-foundation.md](task-execution-foundation.md) · [specs/recurrence-execution-foundation.md](recurrence-execution-foundation.md) · [specs/recurrence-lifecycle-calendar.md](recurrence-lifecycle-calendar.md) · [backend/src/domus/domain/task\_categories.py](../backend/src/domus/domain/task_categories.py) · [backend/src/domus/domain/task\_values.py](../backend/src/domus/domain/task_values.py) · [backend/src/domus/application/task\_category\_commands.py](../backend/src/domus/application/task_category_commands.py) · [backend/src/domus/application/ports.py](../backend/src/domus/application/ports.py) · [backend/src/domus/application/task\_creation.py](../backend/src/domus/application/task_creation.py) · [backend/src/domus/application/calendar\_queries.py](../backend/src/domus/application/calendar_queries.py) · [backend/src/domus/infrastructure/sqlite.py](../backend/src/domus/infrastructure/sqlite.py) · [backend/src/domus/infrastructure/sqlite\_task\_categories.py](../backend/src/domus/infrastructure/sqlite_task_categories.py) · [backend/src/domus/infrastructure/sqlite\_task\_records.py](../backend/src/domus/infrastructure/sqlite_task_records.py) · [backend/src/domus/infrastructure/sqlite\_calendar.py](../backend/src/domus/infrastructure/sqlite_calendar.py) · [backend/src/domus/entrypoints/task\_category\_http.py](../backend/src/domus/entrypoints/task_category_http.py) · [backend/src/domus/entrypoints/task\_http.py](../backend/src/domus/entrypoints/task_http.py) · [backend/src/domus/entrypoints/task\_dto.py](../backend/src/domus/entrypoints/task_dto.py) · [frontend/src/domain/tasks.ts](../frontend/src/domain/tasks.ts) · [frontend/src/domain/calendar.ts](../frontend/src/domain/calendar.ts) · [frontend/src/presentation/domus-tasks.ts](../frontend/src/presentation/domus-tasks.ts) · [frontend/src/presentation/domus-calendar.ts](../frontend/src/presentation/domus-calendar.ts) · [tests/backend/test\_task\_categories.py](../tests/backend/test_task_categories.py) · [docs/tasks/calendar.md](../docs/tasks/calendar.md) · [tests/fixtures/sqlite/v14.sql](../tests/fixtures/sqlite/v14.sql)

## 16. Acceptance scenarios

1. Given genuine schema-14 data containing tasks, tags, snapshots, fixed materialization, and original receipts, when migration succeeds, then those facts and receipts remain intact and legacy work has no category; when an injected migration failure occurs, then the exact original bytes and schema remain.
2. Given a foreign or archived category, when an author assigns it or a reader applies it to a protected calendar query, then the request is rejected without losing the task draft or exposing foreign records. Given an active category, only a current task administrator can create, rename, or archive it; a stale revision conflicts, and retry after a lost response recovers the same operation.
3. Given ordinary, fixed, or relative task creation, when an author omits classification or selects an active category, then the resulting work has the corresponding unclassified or exact category reference. Renaming or archiving does not alter issued task snapshots or original evidence.
4. Given a protected calendar query combining category, timing, state, priority, and member filters, when results are paginated, then every page applies the same authorized predicate and reports matching entries, event count, and distinct occurrence count.
5. Given either browser composition, when a user opens task creation and the calendar, then localized accessible category controls show active choices and the unclassified option, invalid selection preserves the draft, and the calendar displays only authorized filtered results.
6. Given an issued category reference and a compatible rollback, when snapshot inspection and restoration run, then exact references and current schema are verified and original business state is retained; the previous image refuses the newer schema safely.

These scenarios add the seven supplied category cases. Applicable existing task and recurrence cases remain references to their immutable owners and are not rewritten or counted as new definitions.

## 17. Requirements traceability

`task-categories-R1` is exercised by schema-14 migration preservation and injected-failure rollback, and by task creation retaining unclassified legacy work and historical snapshots. `task-categories-R2` is exercised by rejecting foreign or archived assignment and filtering, and by current-administrator authorization, stale-revision conflict, and recovery of the original operation. `task-categories-R3` is exercised by optional classification across ordinary, fixed, and relative creation, and by consistent authorized calendar filtering and counts across pages. `task-categories-R4` is exercised by preserved snapshots and original evidence, localized browser controls with draft retention, and snapshot/rollback/old-image recovery.

The seven new case definitions and their concrete assertions are retained in the host-owned inventory. Existing owner cases remain references. Publication acceptance additionally requires the specification to satisfy the required format; internal and cross-document consistency to be checked; and reciprocal catalog ownership, paths, and evidence to agree with the generated view. The selected source does not verify concrete invocations or completion of these publication outcomes; they remain required observable results, not claims of execution.

| Requirement | Cases |
|---|---|
| task-categories-R1 | task-categories-C01, task-categories-C04, task-categories-C07 |
| task-categories-R2 | task-categories-C02, task-categories-C03 |
| task-categories-R3 | task-categories-C04, task-categories-C05, task-categories-C06 |
| task-categories-R4 | task-categories-C03, task-categories-C04, task-categories-C06, task-categories-C07 |

## 18. Implementation sequence

1. Preserve the reviewed schema-14 migration input byte-for-byte and establish migration, snapshot, rollback, and previous-image refusal evidence before changing persistence. The selected fixture is `tests/fixtures/sqlite/v14.sql`; its SHA-256 is `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a` and its selected-tree blob is `cbaeaf7041e24a1fbc40e124c0c3bde8506b6ab9`.
2. Implement typed category identity, exact active-category authorization, revisioned create/rename/archive commands, and durable SQLite storage with original-operation protection.
3. Extend ordinary, fixed, and relative task authoring to support optional active-category assignment. Keep tags distinct, legacy tasks unclassified, and issued snapshots and receipts intact across rename and archive.
4. Apply category filtering to the protected calendar query. Ensure the authorized predicate and combined category, timing, state, priority, and member filters govern both returned entries and both counts on every page.
5. Connect both browser compositions to localized, accessible category controls; preserve task drafts after invalid selections and render the authorized filtered calendar.
6. Complete migration failure, rollback, restore, stale-command, recovery, and previous-image compatibility evidence; update user and operator guidance and catalog evidence as implementation requires. Do not treat a declared inventory or planned scenario as execution evidence.

## 19. Definition of Done

- [ ] Preserve schema-14 tasks, tags, snapshots, original operations, and exact pre-migration state on injected failure; legacy work remains unclassified.
- [ ] Current authorization, household scope, exact active-category validation, revisions, original-operation recovery, and stale-command behavior satisfy the specified category management and assignment rules.
- [ ] Ordinary and scheduled task journeys retain optional classification; rename and archive preserve issued task snapshots and original evidence. Tags are never category identity.
- [ ] Protected calendar filters produce the same authorized entries, event count, and distinct occurrence count under the combined filters and across pages; foreign or archived categories reveal no data.
- [ ] Both browser compositions pass localized selector, draft-preservation, calendar, accessibility, and invalid-selection acceptance.
- [ ] All seven new cases and applicable retained task and recurrence cases have concrete implementation evidence; requirement-to-case mappings are reciprocal and each case exercises only its mapped requirements. Counts establish inventory structure, not semantic completeness or execution.
- [ ] Migration snapshot inspection verifies category references and current schema; compatible rollback retains business state, and the previous image safely refuses the new schema. The fixture identity and bytes remain unchanged.
- [ ] User, setup, operator, contributor, migration, and recovery documentation is discoverable and agrees with behavior. Existing owners and cases remain intact.
- [ ] The specification satisfies the required format; internal and cross-document consistency is checked; reciprocal catalog ownership, paths, and evidence agree with the generated view. The concrete invocation and prerequisites for the original native SDK publication/validation flow remain unverified in this selected project; declaration of a command is not execution or acceptance.
- [ ] Current required CI, Copilot Verification, and Bugbot pass on the exact implementation commit. No release, deployment, or promotion is inferred.

## 20. References and decisions

- Issue: https://github.com/vypdev/domus/issues/43
- Retained owners: `specs/household-tasks.md` and `specs/task-execution-foundation.md`; recurrence contracts remain in `specs/recurrence-execution-foundation.md` and `specs/recurrence-lifecycle-calendar.md`. Their requirements and cases remain owned there and are referenced, not redefined.
- User guidance: `docs/tasks/calendar.md` currently describes the category filter as a tag filter and must be reconciled with exact category identity while preserving the separate tag field.
- Migration evidence: selected base `c6dcbdf54779f0fe337fab1005ab90470957e40d`; `tests/fixtures/sqlite/v14.sql`, SHA-256 `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`, blob `cbaeaf7041e24a1fbc40e124c0c3bde8506b6ab9`. The fixture contains tagged unclassified work, fixed materialization, and original receipts.
- Decision: categories are household-owned, revisioned references, separate from free-form tags; optional omission keeps work unclassified. Only current authorized administrators manage categories, and assignment and filtering require an exact active category in the current household. Historical snapshots and original-operation evidence remain intact.
- Validation evidence limitation: `specs/README.md` describes specification validation and catalog generation, but the selected root `package.json` does not declare those scripts. The original native SDK invocation, execution prerequisites, and generated-view consistency flow are unverified here; no substitute documentation check establishes SDK consistency.
