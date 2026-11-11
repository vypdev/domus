# Upcoming maintenance qualification

[Issue #100](https://github.com/vypdev/domus/issues/100) adds a protected preview of
open scheduled tasks due from tomorrow through the seventh upcoming local day.
Overview uses the same effective deadlines and detail links as Tasks.

| Published case | Executable evidence |
| --- | --- |
| `overview-maintenance-C01` | The [Overview tests](../../tests/backend/test_task_overview.py) materialize real fixed and relative timed work. They check the seven-day local window across a daylight-saving transition and exclude today's, later, closed and ad hoc work. |
| `overview-maintenance-C02` | Fixed and relative date-only occurrences retain their saved zone and use the effective date after a reviewed move. |
| `overview-maintenance-C03` | The snapshot returns the exact total and earliest 25 ordered rows. Both HTTP compositions deny every group when Tasks read access is revoked. |
| `overview-maintenance-C04` | The [transport tests](../../frontend/tests/task-http.test.ts) reject incomplete groups and duplicate dated rows. [Controller tests](../../frontend/tests/task-overview.test.ts) check retry and retirement of a delayed result. |
| `overview-maintenance-C05` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) opens the exact stored occurrence using desktop keyboard in English and narrow touch in Spanish, then checks Tasks focus. |
| `overview-maintenance-C06` | CI runs the compiled journey in both compositions on amd64 and ARM64. The reviewed Edge artifact pins the installed runtime and UI files. |

The projection streams eligible rows from the authorized household snapshot.
It retains at most 25 upcoming rows and uses the existing storage schema.
