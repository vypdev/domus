# Household task category qualification

The seven cases belong to [the category specification](../../specs/household-task-categories.md).
The [recurrence qualification matrix](recurrence-calendar-qualification.md) preserves the
inherited case IDs and published aliases.

| Case | Executable witness |
| --- | --- |
| task-categories-C01 | `tests/backend/test_schema14_fixture.py` and `tests/backend/test_task_categories.py::test_schema14_category_ddl_rolls_back_to_the_exact_original_bytes` preserve the genuine pre-category database, original rows and bytes under injected DDL failure. |
| task-categories-C02 | `tests/backend/test_task_categories.py::test_protected_category_commands_preserve_exact_history_and_calendar_counts` rejects unavailable category IDs on assignment and calendar reads in both protected compositions. |
| task-categories-C03 | The same protected HTTP test checks current task-administrator authority, stale revision, active name uniqueness and recovery with the exact original key. |
| task-categories-C04 | `tests/backend/test_task_categories.py::test_protected_scheduled_creation_assigns_active_category_and_recovers_original` covers real fixed and completion-relative creation in both modes. The ordinary and materialization tests preserve original labels, tags and receipts through rename and archive. |
| task-categories-C05 | The protected HTTP test combines category, timing, state, priority and member across pages and preserves legacy tags alongside the separate category fields. `tests/backend/test_calendar_queries.py::test_combined_filters_count_actual_performers_independently_of_assignees` distinguishes due assignments and actual performers under the same category. |
| task-categories-C06 | `frontend/tests/e2e/tasks.spec.ts` exercises category recovery, the selector, the protected filter and retention of a stale task and schedule draft in Ingress and standalone, English and Spanish. |
| task-categories-C07 | `tests/backend/test_task_categories.py::test_category_restore_keeps_checkpoint_state_and_recovers_later_archive_by_original_key` and the corrupt-reference snapshot test exercise compatible restore and fail-closed inspection. `tests/containers/test_administration_image.py::test_genuine_schema14_image_refuses_the_upgraded_category_database` uses both packaged compositions and checks that refusal leaves the upgraded database bytes intact. |

The genuine [SQLite schema-14 fixture](../../tests/fixtures/sqlite/v14.sql) has
SHA-256 `acbd5cca8b4ad2177c9ab0fb448efd3502db352081607da1674ce3e39c3acb9a`.
The schema-14 image is built from source commit
`449dc04c17a9c41d949d74cd341bf1e943a2fba9`. The current image uses the exact
checked-out commit. CI runs both source identities on amd64 and ARM64.
