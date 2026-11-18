# Manual automation execution qualification

[Domus #120](https://github.com/vypdev/domus/issues/120) adds explicit manual execution to
the [inactive draft workflow](automation-draft-qualification.md). The
[automation specification](../../specs/household-automation.md) owns requirements
`SDD-I120-U1-R1` through `SDD-I120-U1-R6`.

| Specification case | Verification |
| --- | --- |
| `inventory1-C01` Exact revision | Both HTTP compositions verify initial disabled state, explicit enablement, idempotent configuration, an unchanged enabled revision after editing, rejection of stale control or rule revisions and explicit selection of the next revision. |
| `inventory1-C02` Current access and stock | Both compositions verify current administrator and task authority, a suspended member, checks before original receipt replay, request-time stock changes and task attribution to the invoking member. |
| `inventory1-C03` Result and atomicity | Both compositions verify a matching condition with one ordinary authorized task receipt, an unmatched condition with a recorded no-task result, concurrent duplicate requests, key conflicts, a recoverable lost response and rollback of a task when the outer run receipt fails. |
| `inventory1-C04` Disable and admission | Concurrent disable and run tests exercise whichever writer wins. An already committed run retains its task and original receipt. A later admission under the disabled control is rejected. |
| `inventory1-C05` Accessible operation | The compiled Chromium journeys verify an English desktop keyboard confirmation and narrow Spanish touch, including focus, exact titles and revisions, unmatched stock, reload after an interrupted response, correct task navigation and disabling future runs. |
| `inventory1-C06` Replay and lifecycle | The SQLite tests exercise migration rollback, restart, historical replay without another task, restoration and rollback from [schema 20](../../tests/fixtures/sqlite/v20-inventory-history-source.sql) and [schema 32](../../tests/fixtures/sqlite/v32-automation-execution-source.sql). The schema 32 fixture was generated with the pinned ARM64 Edge.37 runtime at `63890ace59d55ec76e0b9c3c7c832598eeeab7a1`, including two saved revisions and their receipts. |

The exact hexadecimal fixture checks and run outcomes are exercised in
[the command tests](../../tests/backend/test_automation_execution.py),
[the storage tests](../../tests/backend/test_automation_execution_storage.py)
and [the compiled browser tests](../../frontend/tests/e2e/workspace-navigation.spec.ts).
The contributing PR records the two image architectures and the installed Edge candidate.

The HTTP routes use the same active member and request context in
[standalone](../contracts/household-api.openapi.json) and
[Ingress](../contracts/native-household-api.openapi.json).
The control state includes the current saved title, the configured title and two
decimal-string revision fields. An optional stock condition is evaluated from the
same transaction that admits the request. The ordinary task receipt is linked to
the outer run result. Retrying a committed identity returns its original receipt.
A restored historical receipt preserves the result and operation ID, and the UI
labels it as historical. The task link is available for a current committed result.
