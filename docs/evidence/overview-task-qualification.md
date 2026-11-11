# Overview task summary qualification

[Issue #92](https://github.com/vypdev/domus/issues/92) adds assigned and unclaimed
task summaries to Overview. The protected read uses the same Tasks authority as
the detail workspace.

| Published case | Evidence |
| --- | --- |
| `inventory1-C01` | The [protected read tests](../../tests/backend/test_task_overview.py) cover assigned, in-progress and blocked work, reassignment, ordering and exact counts beyond 25. The [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) opens the detail from Overview with desktop keyboard and narrow touch in both compositions. |
| `inventory1-C02` | The protected read tests verify exact totals and bounded Available rows. The [controller and component tests](../../frontend/tests/task-overview.test.ts) distinguish a successful empty result from an unavailable read. The compiled journey retries an interrupted read. |
| `inventory1-C03` | The protected read tests revoke Tasks access in both compositions. The controller tests check late responses, denied and retired contexts. The [HTTP adapter tests](../../frontend/tests/task-http.test.ts) reject incomplete groups and incorrect task states. |

The read uses the current database schema and returns the current member's
task groups from one snapshot. Image CI and installed Edge acceptance provide
separate deployment evidence.
