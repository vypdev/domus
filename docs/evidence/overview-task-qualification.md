# Overview task summary qualification

[Issue #92](https://github.com/vypdev/domus/issues/92) adds assigned and unclaimed
task summaries to Overview. The protected read uses the same Tasks authority as
the detail workspace.

| Published case | Evidence |
| --- | --- |
| `inventory1-C01` | The [protected read tests](../../tests/backend/test_task_overview.py) cover assigned, in-progress and blocked work, reassignment, ordering and exact counts beyond 25. The [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) opens the detail from Overview with desktop keyboard and narrow touch in both compositions. |
| `inventory1-C02` | The protected read tests verify exact totals and bounded Available rows. The [controller and component tests](../../frontend/tests/task-overview.test.ts) distinguish a successful empty result from an unavailable read. The compiled journey retries an interrupted read. |
| `inventory1-C03` | The protected read tests revoke Tasks access in both compositions. The controller tests check late responses, denied and retired contexts. The [HTTP adapter tests](../../frontend/tests/task-http.test.ts) reject incomplete groups and incorrect task states. |
| `overview-task-evidence-C01` | The backend fixture includes 29 assigned and 27 unclaimed tasks. The browser transport verifies a bounded list of 25 and rejects truncated, duplicate and inconsistent replies. |
| `overview-task-evidence-C02` | The browser controller test switches verified subject with a pending read, retires the view during a refresh and resolves each old read after retirement. No old result is published. |

The read uses the current database schema and returns the current member's
task groups from one snapshot. Image CI runs the compiled workflow on amd64 and ARM64.

Home Assistant Supervisor reported `0.0.0-edge.12` before the Ingress
test. The disposable household first showed two empty groups. Creating
two tasks and claiming one gave an exact count of one in each group.
English desktop keyboard selection and narrow Spanish pointer selection
opened the correct task details. After claiming the second task, Overview
showed two assigned and zero unclaimed. The temporary app, its store
source and its test data were removed.
