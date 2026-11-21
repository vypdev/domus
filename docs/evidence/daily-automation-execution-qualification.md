# Daily task automation qualification

Issue [#155](https://github.com/vypdev/domus/issues/155) implements the
[scheduled execution companion](../../specs/automation-scheduled-execution.md).
The retained [automation owner](../../specs/household-automation.md) remains broader:
event triggers, other actions, multi-step/wait/parallel execution and the advanced
editor are not completed by this increment.

## Verification identity and limits

The local full backend campaign passed 5,867 tests against 248 independently
inventoried runtime modules, with all 19,137 statements and 5,148 branches covered.
This includes deterministic writer-order races and terminal cancellation proofs
through all four retirement paths, actual restoration and compatible rollback. The full frontend campaign
passes 2,134 tests across 48 files: all 119 runtime files satisfy all four coverage
metrics (9,296 statements, 8,489 branches, 1,996 functions and 6,760 lines).
Both Python architecture configurations, Ruff and backend mypy also pass.

All 125 compiled protected-server journeys pass in Ingress and standalone. The extended automation journey covers
manual execution, daily enablement, lost committed replies, recovery after reload,
explicit draft reopening, a later manual draft that leaves its daily grant intact,
English keyboard review/cancel/focus and Spanish 390 px dark touch revocation.
The catalog has 37 stories, including eight daily states; its 57 browser cases
pass. Catalog data is fictional. Source-browser identity uses fictional verified
HA providers and owned temporary SQLite stores; neither is installed HA evidence.

The required exact-head CI, both actual CPU images, immutable Edge artifact and
separate installed acceptance remain publication gates. Their results must be
recorded before this qualification is treated as complete. No prior Edge.70 result
qualifies the new schema-36 runtime.

The first source CI exposed a stale product-bundle identity in the navigation
receipt: wheel and both CPU images contained the same newly compiled files, but
the byte guards still expected the previous bundle. That identity must advance
with the newly qualified immutable artifact; the exact byte comparisons remain
required. Source CI is not accepted until those guards and every other suite pass.

Review also reproduced a restoration defect in all four cancellation paths:
disable, regrant, switch to manual and current-grant rejection. An admitted
checkpoint could restore an enabled binding after its queued run had been
cancelled. Cancellation now commits the trigger's original terminal receipt,
audit and acknowledged outbox in the same writer as its control and queue change.
Actual checkpoint activation and compatible rollback must retain that result.
An existing committed task outcome wins over a later cancellation attempt.
The dedicated cancellation and restore cases and full current-source coverage pass;
new immutable images and installed acceptance remain required. Edge.71 was
withheld without installation after this finding.

## Concrete case map

Each of the 48 specification cases appears once below. Parameterized clock,
composition, locale and CPU executions do not increase this inventory count.
The short suite names refer to these actual sources:

- `control`: [daily control](../../tests/backend/test_daily_automation_control.py).
- `execution`: [durable execution](../../tests/backend/test_daily_automation_execution.py).
- `planning`: [pure daily planning](../../tests/backend/test_daily_automation_planning.py).
- `authority`: [narrow rule authority](../../tests/backend/test_scheduled_rule_authority.py).
- `storage`: [SQLite storage and migration](../../tests/backend/test_scheduled_automation_storage.py).
- `restore`: [actual snapshot activation and rollback](../../tests/backend/test_daily_automation_restoration.py).
- `cancellation`: [terminal proof, authority and atomic rollback](../../tests/backend/test_scheduled_automation_cancellation.py).
- `history`: [scoped history](../../tests/backend/test_daily_automation_history.py).
- `http`: [both protected HTTP compositions](../../tests/backend/test_daily_automation_http.py).
- `controller`: [frontend control/recovery](../../frontend/tests/automation-daily-controller.test.ts).
- `view`: [daily presentation and focus](../../frontend/tests/automation-daily-view.test.ts).
- `transport`: [closed transport and journal](../../frontend/tests/automation-daily-http.test.ts).
- `history UI`: [frontend history](../../frontend/tests/automation-daily-history.test.ts).
- `composed`: [application entry composition](../../frontend/tests/page.test.ts).
- `compiled`: [real compiled journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts).
- `catalog`: [built catalog and contrast](../../frontend/tests/e2e/catalog.spec.ts).
- `image`: [packaged owned worker](../../tests/containers/test_daily_automation_image.py).
- `compatibility image`: [old-image refusal and cold protected pair](../../tests/containers/test_app_compatibility.py).

| Case | Observable verification |
| --- | --- |
| inventory3-C01 | `control::test_activator_leaving_does_not_revoke_the_persisted_rule_owned_grant`; `execution::test_rule_owned_execution_continues_after_the_activator_leaves_without_human_proof`. |
| inventory3-C02 | `control::test_grant_creation_rechecks_current_permissions_before_original_lookup`; authority rejects non-task commands and expanded task payloads. |
| inventory3-C03 | `execution::test_disable_serializes_with_the_atomic_task_effect_and_retains_actual_outcome`; authority rechecks disable/regrant/revision/scope before an effect or original lookup. |
| inventory3-C04 | `control::test_saving_a_new_draft_never_rebinds_the_existing_grant`; `http::test_switching_manual_and_daily_revisions_fences_the_real_composed_worker`. |
| inventory3-C05 | `restore::test_actual_restore_preserves_outcomes_and_compatible_rollback_without_a_second_task`; `restore::test_restore_after_admission_cannot_resume_a_run_cancelled_after_the_checkpoint` covers all four cancellation paths through actual activation and rollback. |
| inventory4-C01 | `control::test_household_timing_change_keeps_approved_policy_until_explicit_reviewed_adoption`. |
| inventory4-C02 | The same control test compares both policies and requires the exact reviewed occurrence; controller, view and transport verify deliberate adoption and closed timing proofs. |
| inventory4-C03 | `execution::test_policy_adoption_keeps_an_admitted_runs_original_timing_and_effect`; nominal-frontier tests prevent suppressed dates returning after adoption. |
| inventory4-C04 | `control::test_unavailable_approved_policy_is_exposed_without_substituting_the_proposed_policy`; revocation remains available when both policies fail. |
| scheduled-execution-C01 | `planning::test_strict_future_boundary_and_complete_nominal_facts`. |
| scheduled-execution-C02 | `planning::test_gap_retains_the_requested_date_instead_of_relabelling_the_wall_time`. |
| scheduled-execution-C03 | `planning::test_approved_fold_policy_selects_exactly_one_instant`. |
| scheduled-execution-C04 | Skipped-date, persisted-frontier, clock-rollback and date-line policy-adoption tests in planning and execution. |
| scheduled-execution-C05 | Execution distinguishes offline suppression from ordinary live delay and preserves queued work across a real database reopen. |
| scheduled-execution-C06 | `execution::test_due_trigger_admits_durable_work_before_one_ordinary_task_command`; authority verifies the ordinary task policy, occurrence, receipt and outbox. |
| scheduled-execution-C07 | `execution::test_daily_grouped_conditions_use_real_stock_semantics_without_a_manual_trigger` asserts both matched and no-task outcomes. |
| scheduled-execution-C08 | `execution::test_concurrent_workers_admit_and_execute_one_trigger_once` uses two real SQLite writers. |
| scheduled-execution-C09 | `execution::test_admission_receipt_failure_rolls_back_the_queue_and_cursor_together`. |
| scheduled-execution-C10 | `execution::test_queued_work_survives_a_real_database_reopen_without_becoming_startup_suppression`; image observes admitted work after a three-day restart. |
| scheduled-execution-C11 | Execution injects outer-run receipt failure; authority injects task outbox failure. Both preserve the queue and roll back task facts for an identical retry. |
| scheduled-execution-C12 | `execution::test_startup_suppression_racing_live_admission_has_one_durable_disposition` forces both real writer serialization orders. |
| scheduled-execution-C13 | `execution::test_disable_racing_admission_fences_new_work_or_requires_a_current_revision_review` forces both orders and cancels a reviewed admitted queue. |
| scheduled-execution-C14 | `control::test_disable_cancels_queued_work_and_reenable_uses_a_new_grant_and_future_time`; `cancellation::test_cancellation_proof_and_control_share_one_writer_and_roll_back_together` injects failure at both receipt and outer-control boundaries. |
| scheduled-execution-C15 | HTTP and transport reject extra/duplicate queries, numeric revisions, missing context/CSRF and expanded or mismatched reviewed times. Both OpenAPI documents are checked against actual compositions. |
| scheduled-execution-C16 | Control originals preserve immutable keys and bodies; transport/controller and compiled journey recover one committed enable without another POST. |
| scheduled-execution-C17 | History validates signed scoped cursor pages and rejects invalid bounds, expired/foreign positions and broken retained projections; history UI preserves a failed page for retry. |
| scheduled-execution-C18 | Storage migrates the genuine captured schema-35 fixture, comparing every prior table/column/row; enabled manual1, inactive daily2 and original task/receipts remain. |
| scheduled-execution-C19 | The same storage test independently migrates the schema-20 SQL source and preserves all prior rows. |
| scheduled-execution-C20 | The storage test injects invalid DDL after the first new statement, asserts byte-identical old data, then verifies a supported complete retry. |
| scheduled-execution-C21 | Restore exercises real checkpoint preparation, activation and compatible rollback before/after admission and after completed or cancelled outcomes, without redelivery. Cancellation rejects a checkpoint without its exact terminal proof and retains a historical created-task result instead of relabelling it. |
| scheduled-execution-C22 | Compatibility image builds immutable Edge.70/schema35, snapshots its old data, upgrades it, requires old-launcher refusal without file changes and starts the protected cold old pair. Actual image execution is a separate gate. |
| scheduled-execution-C23 | HTTP verifies current configuration access without task-create can discover an enabled daily1 after latest manual2, although manual invocation is denied; daily revocation succeeds. Composed frontend covers the same capability boundary. |
| scheduled-execution-C24 | HTTP rejects forged identity/grant fields; strict rule codecs reject executable/unknown definitions; authority and integrity reject foreign installation/channel/household facts before effects or disclosure. |
| scheduled-execution-C25 | Execution removes the activating membership and still creates the exact task through the rule-owned principal without human proof. The image fixture rejects any interactive actor request while its worker runs. |
| scheduled-execution-C26 | `authority::test_grant_cannot_expand_its_approved_task_payload` rejects other titles, points, descriptions and materials; non-task action/foreign-command tests reject expanded capabilities. |
| scheduled-execution-C27 | Exact condition product IDs are retained in the grant; integrity rejects missing scoped condition data and execution rejects using a manual rule to probe stock. |
| scheduled-execution-C28 | Controller cancels owned requests and retires private facts on authentication/authority/scope loss; history/transport reject foreign bindings and late callbacks. |
| scheduled-execution-C29 | Compiled English keyboard journey reviews and cancels a daily confirmation, verifies focus, confirms one enable, and retains the existing manual task flow. |
| scheduled-execution-C30 | Compiled Spanish390dark touch revokes the grant; catalog exercises both themes/locales, reduced motion, horizontal bounds, touch targets and measured text contrast. |
| scheduled-execution-C31 | Control rejects stale revisions and elapsed reviewed times; controller, draft composition and view require explicit new review while preserving recoverable fields. |
| scheduled-execution-C32 | Compiled reload recovers the exact original daily key; controller keeps an original-rule read target without selecting or overwriting another draft. |
| scheduled-execution-C33 | Controller preserves verified success after a failed following review or local journal removal, with read-only refresh and no replacement mutation. |
| scheduled-execution-C34 | History distinguishes queued, created, false, cancelled, denied and retained historical facts. Current task read permission and current receipt proof govern task links; unavailable history is not empty. |
| scheduled-execution-C35 | Controller/view cancel adoption without sending; control preserves approved timing until explicit reviewed adoption, and unavailable review can be retried. |
| scheduled-execution-C36 | Image observes each composition's actual owned worker, persistence, admitted restart, daily revocation and manual continuity; existing SIGTERM image fixture now asserts this worker is joined too. |
| scheduled-execution-C37 | The existing amd64/aarch64 CI matrix builds current source and the pinned Edge artifact, then runs image worker and compiled browser journeys. Both actual CPU results remain required. |
| scheduled-execution-C38 | A separately identified immutable installed Edge candidate must create a task at a naturally upcoming minute, show its original history, revoke future work and record scoped cleanup. Pending installed acceptance. |
| scheduled-execution-C39 | Executable import/dependency, closed schema, all-source coverage, wheel/bundle and catalog guards include the new runtime. Artifact hashes, both images and native receipt must agree before acceptance. |

## Migration and recovery inputs

The [schema-35 provenance](../../tests/fixtures/sqlite/v35-daily-automation-source.provenance.json)
records the actual accepted runtime used to generate its SQL, rather than a current
database with a changed version header. Its [generator](../../tests/fixtures/sqlite/generate_v35_daily_automation_source.py)
requires that original runtime. The independent schema-20 source remains unchanged.
The [frozen schema-35 recipe](../../tests/fixtures/schema35-app/Dockerfile) is the exact
previous Edge.70 recipe, outside Supervisor discovery; it is never advanced with the
current artifact declaration.

Schema 36 adds the daily schedule and scheduled-run tables and retained-history
index. No draft is activated by migration. Restore retains valid admitted work,
projects any historical terminal receipt and never resumes cancelled work or
redelivers a committed task. The startup cursor records
skipped nominal dates, including dates coalesced by a time-zone change. A future
adoption or new grant cannot resurrect them.

## Contributor checks and operating guidance

Use the repository's locked environments. Backend qualification is the full
`pytest tests/backend --cov=domus --cov-branch` campaign followed by
`domus-check backend-coverage --report <actual-json-report>`. Python architecture
uses `lint-imports --config architecture/python-application.ini --no-cache` and
`lint-imports --config architecture/python-tooling.ini --no-cache`.
Frontend qualification uses `pnpm check:frontend`, `pnpm test:frontend`,
`pnpm build:frontend`, `pnpm test:frontend-entry`, `pnpm build:frontend-catalog`
and `pnpm test:frontend-catalog`. The self-hosted image job supplies actual current,
pinned and immutable schema-35 images to `pytest tests/containers --no-cov`.
No coverage, retry, runner-placement or required-job policy is weakened.

The [user guide](../user-guide.md#enable-and-manage-a-daily-task),
[operator guide](../operations.md#daily-automation-operation-and-recovery) and
[architecture](../architecture.md#one-automation-engine-two-editors) explain the
same grant, future-time, startup and recovery semantics. Public docs and catalog
metadata must retain this bounded daily scope until the broader owner is delivered.
