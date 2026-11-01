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
| backend/src/domus/domain/recurrence_planning.py | update |
| backend/src/domus/domain/recurrence_records.py | create |
| backend/src/domus/infrastructure/sqlite.py | update |
| backend/src/domus/infrastructure/sqlite_snapshots.py | update |
| backend/src/domus/infrastructure/sqlite_recurrence.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_schema.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_records.py | create |
| tests/backend/test_sqlite_recurrence.py | create |
| tests/backend/test_recurrence_records.py | create |
| tests/backend/test_sqlite_recurrence_records.py | create |
| tests/backend/test_sqlite_recurrence_integrity.py | create |
| backend/src/domus/infrastructure/sqlite_recurrence_integrity.py | create |
| tests/fixtures/sqlite/v7.sql | create |
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
| docs/tasks/migration.md | update |
| docs/evidence/recurrence-execution.json | update |

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

## 19. Definition of Done

- [ ] The four additional cases and every retained requirement/case have truthful current-source evidence; no checkpoint is described as full feature acceptance.
- [ ] Supported first-party coverage is 100% globally/per module; strict types, real architecture contracts and all applicable current-head CI Check suites pass.
- [ ] Original format, consistency and catalog checks pass without changing Copilot resources or weakening limits.
- [ ] Actual production composition, source/restore reconciliation and runtime/UI/HA acceptance are recorded when implemented.
- [ ] No unresolved Bugbot finding remains before merge; reported Copilot limitations keep their actual scope.
- [ ] Necessary evidence and rollback pairs are retained and owned temporary producers are cleaned.

## 20. References and decisions

This companion follows the same immutable retained owners and confirmed product decisions. New record format, byte bound, scoped evidence binding and sequential schema ownership are maintainer engineering proposals, not new owner answers. No product choice is pending. The Action owns SDD publication and remote branch admission. The submitted companion is review input; local validation does not publish it or establish runtime acceptance.
