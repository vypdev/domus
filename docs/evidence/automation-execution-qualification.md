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

## Temporary storage contention

[Domus #152](https://github.com/vypdev/domus/issues/152) qualifies the existing
storage contention contract without changing the application, its SQLite timeout,
or automatic retry behavior. The [second destination CI attempt after #151](https://github.com/vypdev/domus/actions/runs/44857739112/attempts/2)
reported 5,640 passed tests and one failure: the duplicate-run test required both
concurrent requests to return immediately with HTTP 200, although one request
received the documented HTTP 503 `storage_busy` response. The first attempt timed
out; the available observations do not establish its physical cause.

The command tests retain their original unrestricted races and additionally hold
a real SQLite receipt writer in its uncommitted transaction. An event releases
that writer only after the competing HTTP call finishes, exercising the actual
250 ms busy timeout in both standalone and Ingress. No response is replaced with a
fabricated success or rejection.

| Case | Required observations |
| --- | --- |
| Duplicate run | One accepted automation receipt and ordinary task receipt, exactly one definition, occurrence and pending task event, and their two audit entries. A contender may return 503 only with `storage_busy` and `Retry-After: 1`. After both calls finish, one explicit retry of its unchanged body and idempotency key must return the exact accepted original without another effect or audit entry. Reusing the key for a different request still returns `idempotency_conflict`. |
| Run before disable | The admitted task and original receipt survive. If disabling temporarily returns 503, one explicit unchanged retry disables the control without changing task, stock or pending effects; only the disable audit entry is added. A later run is rejected. |
| Disable before run | A temporarily rejected run has no original receipt. One explicit unchanged retry after the disable commits returns `automation_disabled`, with no task, event or run audit entry. The control remains disabled at revision 2. |

The controlled reproduction retained the old immediate-success assertions and
failed six forced-contention cases, while the four unrestricted races passed.
With the corrected observations, all ten race cases passed. The complete command
file and existing storage-contention HTTP tests then passed all 36 cases. These
local results do not substitute for the complete CI and review of the contributing
commit or the exact destination commit after its normal merge.
