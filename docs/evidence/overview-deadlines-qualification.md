# Overview deadline qualification

[Issue #96](https://github.com/vypdev/domus/issues/96) shows open tasks due
today or overdue in the protected Overview summary.

| Published case | Executable evidence |
| --- | --- |
| `overview-deadlines-C01` | The [protected Overview tests](../../tests/backend/test_task_overview.py) classify deadlines immediately before and at the observation instant and at the household's midnight on a daylight-saving transition day. Undated and closed work stays outside both deadline groups. |
| `overview-deadlines-C02` | Fixed and relative date-only cases apply a reviewed date move and compare the saved time zone's day with the household's day. The cases verify date-only precision, one clock observation per summary and the transition to overdue after the local day. The owning task list and detail display the same effective date. |
| `overview-deadlines-C03` | Ingress and standalone HTTP cases verify exact totals and 25 visible items for groups with more matching work. Revoking Tasks read access denies the entire projection. |
| `overview-deadlines-C04` | The [transport tests](../../frontend/tests/task-http.test.ts) reject partial groups and malformed, conflicting or duplicate deadlines. [Controller tests](../../frontend/tests/task-overview.test.ts) discard delayed results after context retirement. |
| `overview-deadlines-C05` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) retries the unavailable read, opens the exact overdue item with English desktop keyboard input and opens the exact item due today with narrow Spanish touch input. Both use the existing Tasks detail and focus. |
| `overview-deadlines-C06` | Image CI runs the compiled journey on amd64 and ARM64 with Ingress and standalone. |

The read uses the existing SQLite schema. It counts eligible tasks from
one authorized snapshot and keeps at most 25 items per group in memory.
