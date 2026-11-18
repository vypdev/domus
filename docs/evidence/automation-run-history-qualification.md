# Manual automation run history qualification

[Domus #122](https://github.com/vypdev/domus/issues/122) lets a member review
their own explicit manual runs for one saved rule. The
[automation specification](../../specs/household-automation.md) defines the
`manual-run-history` requirements and acceptance cases.

| Case | Verification |
| --- | --- |
| `manual-run-history-C01` | The protected HTTP tests select one rule with two authorized members and a second rule. Each member sees only their own results for the selected rule. An unused rule has an empty history. |
| `manual-run-history-C02` | The same tests revoke manual access between pages. Separate task-read revocation leaves the original task decision visible while the task link disappears. The browser tests also retire an open page and its pending read when the same member's verified authorization changes. |
| `manual-run-history-C03` | The original receipts remain in descending commit order when a new run arrives between pages. Tests verify the first page, the lookahead cursor, one-row continuations, and the supported page bounds. |
| `manual-run-history-C04` | Cursor checks cover a different rule, member and page size, expiry and signing-key rotation. The browser controller can restart from recent results. |
| `manual-run-history-C05` | The stored time, exact revision, task decision and receipt survive a rule edit, disabled control and restart. A history request leaves receipts, audit and task state untouched. |
| `manual-run-history-C06` | The SQLite activation test restores a snapshot between two runs. One current result remains linked to its original task. The later retained result appears once, keeps its original outcome and has no task link. |
| `manual-run-history-C07` | The compiled workspace journey exercises the English keyboard, Spanish on a narrow touch viewport, a failed older-page read and retry, exact task navigation and clearing the view when switching to a different rule. Both HTTP compositions use the same read. |
| `manual-run-history-C08` | The contributing pull request records the exact candidate's image checks and separately installed Home Assistant Edge acceptance, including cleanup. |

The [protected HTTP tests](../../tests/backend/test_automation_run_history.py)
and [SQLite activation tests](../../tests/backend/test_automation_execution_storage.py)
exercise the original receipt and retained evidence. The
[frontend tests](../../frontend/tests/automation-run-history.test.ts) and
[workspace browser tests](../../frontend/tests/e2e/workspace-navigation.spec.ts)
qualify the selected rule, user session and recovery states.

`GET /api/v1/automation/drafts/{rule_id}/runs` uses the current household
context in [Ingress](../contracts/native-household-api.openapi.json) and
[standalone](../contracts/household-api.openapi.json). The default is 25
results and the maximum is 100. Continuation is bound to the authenticated
member, rule, and page size and expires within five minutes. The read uses
existing current and retained receipts in SQLite schema 33.
