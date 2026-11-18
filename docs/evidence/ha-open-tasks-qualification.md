# Home Assistant open-task list qualification

[Domus #137](https://github.com/vypdev/domus/issues/137) implements the
[open household task companion specification](../../specs/home-assistant-todo-list.md).
The [task list guide](../tasks/ha-open-tasks.md) describes the grant, connection,
read-only behavior and recovery in English and Spanish.

| Case | Verification |
| --- | --- |
| ha-open-tasks-C01 | Real SQLite fixtures on Ingress and standalone compare every open state with the authoritative occurrence records. They exclude completed, cancelled and skipped work, distinguish same-title occurrences, and retain identity across state changes and reopening. Definition edits preserve existing occurrence snapshot titles. Core verifies stable UIDs when a response title changes. |
| ha-open-tasks-C02 | A snapshot returns exactly 1,000 open occurrences through 101-record queries using one SQLite read connection. This crosses the first 25 and the 101/102 boundary. The 1,001st occurrence returns unavailable with zero partial items. Core accepts 1,000 and rejects 1,001. |
| ha-open-tasks-C03 | Both protected routes verify default-disabled, missing, rotated, foreign, cross-channel and wrong-purpose grants. Calendar, deadlines, low-stock and shopping projections retain independent credentials. |
| ha-open-tasks-C04 | Only title, state and opaque UID are published. Repeated successful and failed reads preserve persisted facts. A task bearer cannot authorize the ordinary task write route. Core exposes zero mutation features and rejects native add, complete and delete operations. |
| ha-open-tasks-C05 | Disposable Core verifies English and Spanish state labels, entity names, stable source and occurrence identities, bearer rotation, separate sources and a fresh process restart with the saved entries. |
| ha-open-tasks-C06 | Core distinguishes empty, malformed, denied and recovered reads. It rejects duplicate JSON keys, unexpected fields, invalid titles, states and UIDs, duplicate occurrences, oversized and invalid UTF-8 bodies. Failed reads hide cached items and clear the item subscription. Unload stops scheduled refreshes. |
| ha-open-tasks-C07 | The packaged acceptance connects disposable Core to isolated Supervisor and HTTPS standalone compositions for both Edge and Stable fixture data. Image architecture and separately installed Edge acceptance are recorded with the final candidate. |

The [artifact declaration](../../addon-edge/artifact.json) identifies the exact
Edge runtime, source archive, wheel and installed files. The projection uses
SQLite schema 34.

Local disposable Core `2026.10.4` passed with all ten authored Python modules
at 100% statement and branch coverage, covering 581 statements and 136 branches.
