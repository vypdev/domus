# Recurrence execution continuation and owned storage boundaries

- Status: Draft
- Date: 2026-11-01
- Catalog capability ID: recurrence-calendar
- Related issue: https://github.com/vypdev/domus/issues/20
- Retained execution owner: specs/recurrence-execution-foundation.md
- Publication path: specs/recurrence-storage-continuation.md
- Blocking product decisions: none; implementation and acceptance remain outstanding.

## 1. Executive summary

Continue the complete existing recurrence execution contract after its deliberately partial planning checkpoint. This is an explicitly approved companion under the same recurrence-calendar capability. It retains the existing execution companion and original owner verbatim. Preserve the retained eight RCE requirements, 52 companion cases and 37 original owning cases verbatim. Four additional cases below refine independent storage boundaries; they do not replace, recount or certify those retained journeys.



### Review correction of the first publication

The first Action publication at 0806a38f8a2de1f102a017bff25ad6856fb17bcd generated four broader integration scenarios already required by the retained execution owner. They remain required through that owner; they are not four additional independent journeys. This explicit contributor revision replaces their duplicate counting with the four independently refined storage boundaries below. Original publication bytes remain in Git history. Its broad REC-CONT requirements remain summaries of retained RCE scope, not deleted product behavior. Neither retained owning document is edited.

| First-publication case reference | Retained owning coverage | Treatment |
|---|---|---|
| recurrence-storage-continuation-C01 | recurrence-execution-C45, recurrence-execution-C46 | Migration/rollback integration alias; required, not an additional counted journey. |
| recurrence-storage-continuation-C02 | recurrence-execution-C17, recurrence-execution-C18, recurrence-execution-C19 | Concurrent atomic/restart integration alias; required, not an additional counted journey. |
| recurrence-storage-continuation-C03 | recurrence-execution-C21, recurrence-execution-C31, recurrence-execution-C32, recurrence-execution-C35 | Reviewed schedule/state integration alias; required, not an additional counted journey. |
| recurrence-storage-continuation-C04 | recurrence-execution-C37, recurrence-execution-C38, recurrence-execution-C39, recurrence-execution-C43 | Protected calendar integration alias; required, not an additional counted journey. |

The four newly defined IDs are distinct from those published aliases. A runtime test may cover several retained obligations but remains one executed journey. English and Spanish UI with English fallback remain confirmed under the owning product decisions. This storage increment does not introduce a new UI locale decision.

## 2. Problem, current behavior, and evidence

The verified immutable development base is commit 3131810082760a98ee4af66f11bb65eaac49cc3b, tree c18c57b60e20ccbc83d61464ab5fe623c8ed1713. It contains 453 tracked files and both approved foundation merges. The same tree passed 3,398 backend tests across 117 authored modules, with 100% statement and branch coverage (8,410 statements and 2,406 branches). These are foundation results, not durable recurrence acceptance.

Pure rule validation, finite original-period expansion, pinned time resolution and bounded side-effect-free planning now exist. SQLite is still schema 7. There is no recurrence repository, durable materializer, lifecycle consumer, calendar query/API or composed recurrence runner. The earlier 430-blob archive and bootstrap baseline in the retained companion are historical evidence only.

Five preliminary source/test/fixture files are privately retained with hashes and a Git stash. Their initial missing-symbol collection failure is not a passing test or completed implementation. Resume them only after this issue's normal companion publication and exact Action-managed branch admission. The genuine schema-7 fixture was generated from the prior schema-7 source before new DDL; existing historical fixtures remain immutable.

## 3. Actors, surfaces, and terminology

Human configuration and protected result recovery retain current HA and household authority. Local maintenance receives a separately composed technical capability bound to the actual installation, channel and household; a record constructor or submitted selector grants no authority. A nominal slot identifies one obligation under a pattern revision. A record revision supports current-state concurrency; pausing alone must not change nominal identity.

## 4. Goals

| Requirement | Behavior |
|---|---|
| recurrence-storage-R1 | Enforce the aggregate canonical storage/receipt payload bound independently of each accepted field and batch count. |
| recurrence-storage-R2 | Reject noncanonical, unknown-version or header/body-inconsistent stored recurrence records without defaulting or coercion. |
| recurrence-storage-R3 | Refuse ordinary operations on an owned schema-7 source until explicit atomic schema-8 initialization succeeds. |
| recurrence-storage-R4 | Bind each committed current nominal slot to its exact scoped original command evidence, independently of task-row existence. |

All retained RCE-01 through RCE-08 work remains required: authorized scheduled creation/reviewed attachment, fixed and completion-relative persistence, atomic materialization/source processing, restore non-recreation, previews/exceptions, classification/calendar queries, strict HTTP and both persistent runners. The full first all-domain UI/HA/Stable-Edge release remains required. This appendix neither closes those requirements nor claims consumer delivery.

## 5. Current versus proposed product journey

Current planning returns bounded values without saving tasks. The intended complete journey remains: current-authorized configuration, durable rule, bounded atomic execution and truthful protected calendar facts. Storage tests first establish owned persistence invariants; they cannot stand in for the actual human journey, HTTP authorization, runner composition or browser acceptance.

## 6. Functional behavior and state model

Persist typed fixed-rule, progress and nominal-slot records through the existing unit of work. Separate mutable record revision from pattern revision. Preserve canonical date-only versus naive local-time tags, full time-policy snapshots and original resolved facts; date-only values do not acquire a fabricated midnight instant. Fixed cursor binding includes the complete pattern and time policy.

Use explicit versioned closed encodings and a maximum 65,536-byte canonical JSON document. A 1,000-slot run is a work limit, not permission to put 1,000 arbitrarily large results into one receipt. Commit bounded per-slot results with stable original command keys; retain exact receipt, audit and outbox evidence in the same transaction. Validate scoped rule, definition, occurrence, installation and channel relationships. Deferred evidence constraints must hold at commit, including independently opened connections.

Supported source migration adds recurrence tables atomically as schema 8 without replacing existing tables or receipts. Normal read/write transactions reject schema 7 before constructing usable recurrence repositories. Migration failure preserves original business rows and version. Unknown or future layouts and malformed records fail closed. Full snapshot verification must validate the new physical and semantic records before prepared activation.

## 7. Non-goals and retained scope

No Copilot code, configuration, credential, bound or lifecycle change is authorized. The existing gateway remains integrated. No release, owner HA update or deployment is implied. Storage constructors and synthetic repository fixtures do not impersonate HA accounts. Unfinished execution, relative lifecycle, preview, calendar/API, native/standalone, UI, HA and launch acceptance remain explicit work under the retained owners, not exclusions from the product.

## 8. Clean Architecture

Domain records and stable slot/cursor identity remain pure Python values. Application ports expose semantic scoped persistence and current authorization; they do not import SQLite, web frameworks, HA clients or timezone providers. Infrastructure implements strict encoding, ownership inspection, schema migration, transactions and snapshot verification. Existing composition owns clocks, identifiers, installation/channel and eventual runner disposal. Entry points cannot construct technical authority from request fields.

## 9. UX and API contract

Retain the owner's truthful pending, incomplete, conflict, unavailable and historical-effect-absent states. There is no new user-visible endpoint in a storage-only checkpoint. Later EN/ES interfaces use English fallback and the same actual protected use cases; a stored fixture is not evidence of an interactive or HA calendar surface. Recovery requires current authority before original protected results are disclosed.

## 10. Failure, recovery, and cleanup

Rule, cursor, task, slot and original operation evidence commit or roll back together. Concurrent state updates use expected revisions; scoped immutable identity and creation facts cannot be rewritten. Restart uses independent durable reads. Restoring older business state preserves later original proofs so a missing processed effect is never silently recreated. Complete restore/source reconciliation remains required beyond this repository boundary. Retain compatible application/data/generation rollback pairs and only remove owned temporary producers after necessary evidence is preserved.

## 11. Security, permissions, and privacy

Reject malformed stored JSON, alternate tag/time encodings, unknown fields/versions, bool-as-integer revisions, mismatched headers and foreign scope. Enforce aggregate byte bounds before business writes; never silently truncate. New records do not widen existing human permissions, outage writes or receipt access. No submitted actor, channel, installation or household selector becomes technical authority. Keep owner identity/browser artifacts private.

## 12. Observability and operational UX

Expose only safe bounded failure codes and explicit retained-state facts. A storage rejection is not an empty calendar or successful delivery. Later execution telemetry retains real last committed position, backlog and source/restore attention. Case counts, executed tests, coverage and runtime acceptance remain separate evidence.

## 13. Compatibility, migration, rollout, and rollback

Issue 20 implements the original issue 17 schema-8 contract. Issue 21 continues the original issue 16 administration contract only after the actual schema-8 merge, then uses schema 9. The model-only checkpoint merges left schema 7 and did not perform either migration.

Preserve historical schemas 1 through 7 and the unchanged existing fixture bytes. Add the genuine schema-7 fixture rather than rewriting prior fixtures to resemble a later layout. Verify explicit migration, failure rollback, strict current-schema transactions and semantic snapshots. Actual old schema-7 images, including retained Edge.5, refuse schema 8. Rollback selects the compatible complete application/database/generation pair; never edit a version number to downgrade. Both actual image architectures and persistent compositions need current-source tests before claiming a new package. No automatic backup retention policy is invented.

## 14. Testing strategy and numeric budget

The retained 52 companion cases and 37 original owning cases remain required. The following 4 distinct cases add storage-specific boundaries only. Do not count a parameterization or a test that also covers a retained scenario as another independent journey. Begin with meaningful failing tests and require 100% supported first-party statement/branch coverage globally and per module, strict typing, architecture/privacy negatives and every-PR CI Check.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Storage boundary | 1 | Observable scenarios in the case inventory. |
| Record integrity | 1 | Observable scenarios in the case inventory. |
| Migration entry | 1 | Observable scenarios in the case inventory. |
| Evidence binding | 1 | Observable scenarios in the case inventory. |
| Total | 4 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| recurrence-storage-C01 | Storage boundary | recurrence-storage-R1 | Individually valid fields combine into a canonical document above 65,536 UTF-8 bytes; serialization rejects it before any business write, and a bounded run does not pack oversized aggregate results into one receipt. |
| recurrence-storage-C02 | Record integrity | recurrence-storage-R2 | A stored tagged date/time or revision has an alternate encoding, unknown field/version or header/body mismatch; a fresh repository read fails safely without coercion, defaults or data replacement. |
| recurrence-storage-C03 | Migration entry | recurrence-storage-R3 | An owned genuine schema-7 database is opened through ordinary read and write transactions before initialize; both refuse it without changes, while explicit successful migration enables schema-8 transactions. |
| recurrence-storage-C04 | Evidence binding | recurrence-storage-R4 | A current nominal slot names a real same-household occurrence but its exact scoped recurrence command receipt is absent or replaced by another command namespace; commit rejects it and leaves no slot or unrelated evidence changes. |

Use real independent SQLite connections and exact before/after version/row checks. These case descriptions are planned, not executed. The complete retained contract still needs concurrency/crash/restoration, actual source lifecycle, HTTP/security, both runtimes/images and browser/HA acceptance where applicable.

## 15. Documentation and discoverability

| Path | Change |
|---|---|
| specs/recurrence-storage-continuation.md | update |
| specs/recurrence-execution-foundation.md | reference |
| specs/recurrence-calendar.md | reference |
| specs/household-administration.md | reference |
| specs/catalog.json | update |
| specs/CATALOG.md | update |
| .dockerignore | create |
| .github/workflows/ci_check.yml | update |
| tests/python/test_ci_contract.py | update |
| frontend/tests/e2e/entry.spec.ts | update |
| tests/browser/entry_server.py | update |
| tests/fixtures/current-app/Dockerfile | create |
| tests/containers/test_app_image.py | update |
| tests/containers/test_app_compatibility.py | update |
| tests/containers/restore_fixture.py | update |
| tests/containers/test_recurrence_image.py | create |
| addon-edge/Dockerfile | reference |
| docs/evidence/recurrence-storage.json | create |
| backend/src/domus/application/fixed_recurrence.py | update |
| backend/src/domus/application/ports.py | update |
| backend/src/domus/application/recurrence_ports.py | update |
| backend/src/domus/application/recurrence_commands.py | create |
| backend/src/domus/application/fixed_materialization.py | create |
| backend/src/domus/application/fair_recurrence.py | create |
| backend/src/domus/application/relative_recurrence.py | create |
| backend/src/domus/application/commands.py | update |
| backend/src/domus/application/task_creation.py | create |
| backend/src/domus/application/task_commands.py | update |
| backend/src/domus/application/task_authorization.py | update |
| backend/src/domus/domain/recurrence_planning.py | update |
| backend/src/domus/domain/recurrence_records.py | create |
| backend/src/domus/domain/recurrence_membership.py | create |
| backend/src/domus/domain/recurrence_frontier.py | create |
| backend/src/domus/domain/relative_recurrence.py | create |
| backend/src/domus/domain/tasks.py | update |
| backend/src/domus/domain/task_events.py | update |
| backend/src/domus/domain/recurrence_time.py | update |
| backend/src/domus/domain/recurrence_rules.py | update |
| backend/src/domus/infrastructure/recurrence_time.py | update |
| backend/src/domus/infrastructure/recurrence_worker.py | create |
| backend/src/domus/composition/recurrence.py | create |
| backend/src/domus/composition/server.py | update |
| backend/src/domus/composition/ingress.py | update |
| backend/src/domus/infrastructure/sqlite.py | update |
| backend/src/domus/infrastructure/sqlite_receipts.py | create |
| backend/src/domus/infrastructure/sqlite_snapshots.py | update |
| backend/src/domus/infrastructure/sqlite_recurrence.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_schema.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_records.py | create |
| tests/backend/test_sqlite_recurrence.py | create |
| tests/backend/test_recurrence_records.py | create |
| tests/backend/test_recurrence_creation.py | create |
| tests/backend/test_fixed_materialization.py | create |
| tests/backend/test_fixed_materialization_shutdown.py | create |
| tests/backend/test_fair_recurrence.py | create |
| tests/backend/test_fair_recurrence_boundaries.py | create |
| tests/backend/test_recurrence_frontier.py | create |
| tests/backend/test_recurrence_worker.py | create |
| tests/backend/test_recurrence_runtime.py | create |
| tests/backend/test_recurrence_canonical_storage.py | create |
| tests/backend/test_storage_contention_http.py | create |
| tests/backend/test_relative_recurrence_records.py | create |
| tests/backend/test_relative_recurrence_planning.py | create |
| tests/backend/test_recurrence_local_instant.py | create |
| tests/backend/test_recurrence_cursor_integrity.py | create |
| tests/backend/test_recurrence_cursor_evidence.py | create |
| tests/backend/test_recurrence_until_proof.py | create |
| tests/backend/test_recurrence_slot_membership.py | create |
| tests/backend/test_sqlite_recurrence_records.py | create |
| tests/backend/test_sqlite_recurrence_integrity.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_integrity.py | create |
| tests/fixtures/sqlite/v7.sql | create |
| tests/fixtures/sqlite/unreleased-c581-schema8.sql | create |
| tests/fixtures/sqlite/unreleased-b2bcc69-schema8.sql | create |
| tests/backend/test_sqlite_transactions.py | update |
| tests/backend/test_sqlite_snapshots.py | update |
| tests/backend/test_activation_compatibility.py | update |
| tests/backend/test_restore_source.py | update |
| tests/backend/test_sqlite_history.py | update |
| tests/backend/test_sqlite_identity.py | update |
| tests/backend/test_sqlite_recovery.py | update |
| tests/backend/test_sqlite_task_integrity.py | update |
| tests/backend/test_sqlite_task_materials.py | update |
| tests/backend/test_sqlite_task_reviews.py | update |
| tests/backend/test_task_restoration.py | update |
| docs/architecture-recurrence.md | update |
| docs/evidence/recurrence-creation.json | create |
| docs/evidence/recurrence-materialization.json | create |
| docs/evidence/recurrence-fairness.json | create |
| docs/evidence/recurrence-lifecycle.json | create |
| docs/evidence/recurrence-review-corrections.json | create |
| docs/evidence/recurrence-relative-planning.json | create |
| docs/evidence/recurrence-cursor-integrity.json | create |
| docs/tasks/migration.md | update |
| docs/evidence/recurrence-execution.json | update |
| docs/evidence/recurrence-until-integrity.json | create |

Existing retained path declarations describe their original publication baseline; the table above identifies this continuation's actual new and existing storage paths at the immutable base. Declare any additional real implementation/test path before committing it. Update exact evidence and current acceptance limits without relabeling historical results.

## 16. Acceptance

1. Given independently valid input fields whose canonical combined representation exceeds the byte bound, when persistence is attempted, then it fails before business changes and does not truncate the result.
2. Given a corrupt/noncanonical recurrence document, when an independent repository reads it, then the read returns a safe storage failure and preserves the original source bytes.
3. Given an owned schema-7 source, when ordinary transactions run before explicit initialization, then they refuse the old schema; successful explicit migration enables the same source under schema 8.
4. Given a nominal slot with a valid occurrence but missing or wrong-namespace command proof, when its transaction commits, then deferred evidence validation rejects the transaction with no partial slot.

Execute and retain current-source results before marking these scenarios accepted. Passing them alone does not complete retained RCE requirements or release acceptance.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| recurrence-storage-R1 | recurrence-storage-C01 |
| recurrence-storage-R2 | recurrence-storage-C02 |
| recurrence-storage-R3 | recurrence-storage-C03 |
| recurrence-storage-R4 | recurrence-storage-C04 |

The retained owner's reciprocal mappings remain unchanged. New mappings above cover only this companion's four independent refinements, not another execution count for the retained cases.

## 18. Implementation sequence

After normal branch admission: restore the privately preserved test-first draft; implement pure records and scoped SQLite adapter; implement schema-8 migration and complete snapshot verification; exercise negative boundaries and real transactions; then continue all retained authorized execution, relative lifecycle, restoration, preview, calendar/API and runner work. Update evidence, documentation and applicable images before review. Administration schema 9 follows the actual recurrence merge.

The next application increment implements new active fixed-task creation through existing task-create, configuration-override and inventory-link authority. It saves the shared task definition, rule, unconsumed cursor and original command evidence together. It deliberately creates no manual initial occurrence; actual materialization remains required. Date-only configuration still validates its actual pinned zone/data policy without storing a fabricated instant. Preflight provider work holds no writer lock, and current local authority is checked again in the commit. Authorized original receipts precede provider work; changed keys/payloads and revoked authority retain existing semantics. Draft configuration, relative creation, reviewed attachment, public HTTP/operation queries and composed runners remain unfinished.

Bugbot identified a storage boundary missing from the first kernel: a correctly scoped slot could name a nominal outside its pattern or COUNT/UNTIL end. Validate actual finite-period candidate membership and nominal rank in the pure record constructor, so closed decoding and checkpoint inspection enforce the same invariant. COUNT rank preserves interval phase, initial-period truncation, omitted invalid dates and Gregorian repetition; bounded pure memoization is an optimization, never evidence or authority. Do not weaken the existing slot/receipt/source relationships or alter the schema to mask corrupt records. A codec fixture must itself describe a real candidate. These are refinements of retained RCE/storage integrity obligations, not additional counted product journeys.

The next application step materializes at most one actual fixed obligation or scans at most 64 original periods. Trusted composition supplies its explicit installation/channel/household maintenance scope; no request or stored record grants that capability. External policy/planning work holds no writer lock. Current rule/progress/definition facts and the fixed technical command namespace are checked before original receipt lookup in the writer transaction. A new task, slot, receipt/audit/outbox and progress advance commit together through the shared command boundary. A matching current receipt does not create another task. An actual restored absent-effect receipt advances the reconciled cursor without recreating the task, allocating replacement identities or re-emitting its event; the returned historical status remains explicit. Empty bounded scans retain their own proof and incomplete continuation. Date-only values retain no fabricated deadline instant, and technical maintenance never performs or approves human work. The fair multi-rule production loop, durable attention/calendar projections, relative lifecycle and full runtime surfaces remain unfinished.

The bounded fair application run selects at most 50 active rules and processes at most 1,000 nominal slots globally, including original-proof replay and historical reconciliation. A separate technical period budget defaults to 4,096 and cannot exceed 64,000; empty scans consume it. Horizon defaults to 60 local days within the retained 7..366 bound. Round-robin service shares each selected window. A scoped revisioned frontier records each actually admitted rule before provider work, once per rule in that window; reserving an entire unvisited window is insufficient under repeated interruption. The frontier is selection metadata, not completion or calendar-freshness proof, and has no foreign key to a potentially removed last rule.

Rule snapshots used to compute horizons are rechecked by the step. Cancellation is observed before provider work and again before atomic write admission, including after waiting for a writer; an already admitted atomic effect completes or rolls back. Results report bounded confirmed observations and safe rule-specific attention categories without echoing raw diagnostics. Source failure does not starve peers; scope failure remains fatal. An actual offline restore keeps absent-effect semantics through the global run. No thread, production polling lifecycle or public route is added by this application-run checkpoint.

Selection metadata is added to schema 8 before its first release. Supported historical schemas 1..7 and original fixture bytes remain unchanged. The genuine intermediate c5819b8 schema-8 SQL input was generated under that exact source before this DDL change; normal operations and initialization reject its unknown development layout without modifying it. It is a refusal/rollback control, not a promise to migrate an unreleased layout or permission to edit user_version. The owner remains on the unchanged released schema-7 Edge.5 pair. Complete production scheduling, relative sources, durable calendar/review attention and the remaining retained requirements remain pending.

The next production increment composes that fixed runner into both persistent native and standalone applications. Construction remains inert. The actual ASGI lifespan starts one owned thread; it attempts a bounded run immediately and waits five seconds after each attempt, including unavailable or unconfirmed attempts. This engineering polling interval does not change the rule's business time policy or human permissions. Composition selects only the current household in its trusted installation; unconfigured installations remain unconfigured, and homes with no active rule create no frontier or business effects. No human proof or submitted scope is used for technical execution.

Review identified a strict-storage gap: parsing JSON could normalize altered source bytes before the closed typed codec checked them. Compare the original stored text with the exact canonical representation before constructing any recurrence record. Whitespace, key order and equivalent escaped keys must fail safely in direct rule/progress/slot/frontier reads and full checkpoint validation, without repairing source bytes. Keep existing semantic-negative tests canonically serialized so they continue to exercise typed integrity independently of syntax rejection. This refines recurrence-storage-R2 and retained record integrity, without inventing another product case count.

Concurrent browser evidence also exposes unavailable follow-up reads during a setup winner's commit. An exclusive SQLite writer must yield bounded storage_busy during initial database inspection, not a corruption classification or internal_error. Preserve corrupt-file refusal for other inspection failures. An explicit user status refresh after the two concurrent POST responses can restore verified current facts before inspecting the retained rejection and deliberately replaying the exact original request; it never retries a POST automatically. Verify both read/write repository entry points, actual native/standalone authorization HTTP responses and the real browser flows. The original CI trace has no internal exception stack; the exclusive-lock reproduction establishes the concrete inspection defect rather than proving an unlogged historical stack.

The next relative increment establishes typed rule/progress/source/slot values and read-only successor planning under the complete retained execution contract. LocalInstant retains an actual UTC instant's realized wall time and offset independently of the household's preference for resolving a future repeated time. In particular, actual work in the second autumn fold remains in that fold even when future work uses the first. Integer UTC/local arithmetic, millisecond precision, policy and pinned zone-byte identity are explicit. The UTC epoch can have an actual local basis in late 1969 under a negative offset; that internal fact does not broaden the existing 1970..9999 user-nominal contract.

TaskCycle supplies its original completion snapshot through one shared pure helper used by existing lifecycle validation and the relative source value. Approval and reopening never rewrite actual performed time, performers or snapshotted rules. Planning receives the current cycle: paused/retired rules, closed/rejected cycles and pending at_verification work produce explicit nonready states without provider work. Ready plans use local calendar days from performed_at, preserve milliseconds for time deadlines, keep date-only deadlines as dates even for a wholly missing local date, and reject inconsistent provider facts or overflow. Original cycle identity, not approval time or a generated task ID, determines the successor slot key within its generation. Historical slot values preserve original source facts after later closure; constructing one confers no execution authority.

The shared nominal/resolved PlannedSlot value retains PlannedFixedSlot as a source-compatible name; its encoding and existing fixed rule membership checks remain unchanged. Actual SQLite task lifecycle reads exercise pending, approved and reopened source facts without persisting a relative plan or generating an event. The future durable consumer must revalidate the live cycle and its own retained inbox/closure before command receipt lookup and commit; feeding an old event snapshot alone is insufficient. Relative rule/progress/slot storage, atomic initial creation, original-proof reconciliation, durable source/inbox closure, successor invalidation, global mixed-rule fairness and runtime wiring remain required. No SQLite layout or owner installation is changed by this planning increment.

Further native review identified that a correctly bound fixed cursor could disagree with its consumed nominal rank. Validate the exact original candidate prefix represented by period_index and offset before accepting fixed progress. Reuse the finite Gregorian-cycle/interval-phase rank logic, preserving truncated DTSTART, omitted invalid dates and genuinely empty periods. Reject offsets beyond a period and positions beyond the first exhausted calendar period; do not traverse arbitrary prior history. Count-ended and date-ended cursors must not claim early exhaustion or consume dates beyond their end. An unlimited rule cannot be marked closed inside its representable calendar. Repository progress reads recheck the rule relationship as well as canonical headers, and snapshot validation shares it. These relations establish cursor consistency, not caller authority, original effect proof or complete calendar freshness.

Preserve a real source059 wheel identity when replaying the original negative regression against the prior implementation. An initial test fixture accidentally mixed a real pinned policy with a fixture policy; correct that binding and verify the meaningful original failures against every byte-verified published module. Keep genuine sparse/terminal continuations as positive controls. The new strict read exposes an invalid stored binding as invalid_recurrence_record before the higher-level source check; keep a precise failure assertion for that earlier boundary. These are refinements of retained progress/record integrity, not extra counted product journeys.

The worker carries cancellation into every run and joins before runtime identity/storage disposal and installation-lease release. The lifespan preserves the existing application's state and exits its prior context after stopping the worker, including on startup/application failure. Ordinary failures expose only bounded categories and permit a later attempt; a denied technical scope terminates that worker. Last-run observations remain process-local diagnostics, not durable calendar freshness or delivery proof. Identity-only preview has no worker. Actual current-source image controls exercise both ASGI lifetimes, scoped SQLite work and shutdown. Relative lifecycle, current-authorized calendar/command surfaces, durable attention, configurable household timing defaults and complete product/UI/HA acceptance remain required.

## 19. Definition of Done

Browser CI later recorded a503 rejection whose body was unavailable through Chromium CDP, while the actual application showed the rejected outcome and preserved its draft. Retain that trace; its generic navigation guidance does not establish an actual unexpected navigation. Contention tests may buffer the actual upstream HTTP response before forwarding the same bytes, status and headers to the browser, with redirects and network retries disabled. Preserve real independent SQLite writer contention, browser response checks, exact request metadata, current-authorized replay, draft/journal identity and no-duplicate assertions. A test observation repair changes neither product behavior nor storage timeouts, and adds no counted product journey.

UTC UNTIL continuation additionally retains the actual last included resolved slot and, when discovered, the first excluded candidate at the cursor. The last included instant must not exceed the inclusive cutoff and its nominal rank must equal the consumed count. Closed progress requires the actual excluded boundary, a conservative exhausted-period lower bound or natural calendar exhaustion. A legitimate unclosed cursor after the final included slot remains valid until a later bounded step checks the end. Unproved bootstrap values cannot claim a run or a completed range.

Every actual fixed progress advance, including empty scans and date/count rules, binds its time evidence to the exact original scoped command and operation. Slot and scan receipts retain the evidence core; a current or restored historical original must match before progress is saved. A separate deferred revision-bound evidence header and strict canonical inline document must agree on reads and checkpoint validation. Providers resolve outside the writer; domain records perform no timezone I/O. Restored absent effects remain absent without new identities or delivery.

The evidence table is an unreleased schema-8 layout refinement, not a new released migration or schema9. Preserve the real b2bcc69 source/database pair and reject its previous four-table development layout without changing it. SQLite logical dumps omit header pragmas: a replay fixture must restore the actual original captured application ID and schema value, rather than silently exercising version0. Keep the raw source database unchanged and disclose the first incomplete-dump observation. Existing released1..7 inputs and their migrations remain supported. These integrity refinements add no counted product cases and do not complete retained execution/calendar acceptance.

- [ ] The four additional cases and every retained requirement/case have truthful current-source evidence; no checkpoint is described as full feature acceptance.
- [ ] Supported first-party coverage is 100% globally/per module; strict types, real architecture contracts and all applicable current-head CI Check suites pass.
- [ ] Original format, consistency and catalog checks pass without changing Copilot resources or weakening limits.
- [ ] Actual production composition, source/restore reconciliation and runtime/UI/HA acceptance are recorded when implemented.
- [ ] No unresolved Bugbot finding remains before merge; reported Copilot limitations keep their actual scope.
- [ ] Necessary evidence and rollback pairs are retained and owned temporary producers are cleaned.

## 20. References and decisions

This companion follows the same immutable retained owners and confirmed product decisions. New record format, byte bound, scoped evidence binding and sequential schema ownership are maintainer engineering proposals, not new owner answers. No product choice is pending. The Action owns SDD publication and remote branch admission. The submitted companion is review input; local validation does not publish it or establish runtime acceptance.
