# Purchase balance cancellation qualification

[Issue #80](https://github.com/vypdev/domus/issues/80) lets a shopping manager
close the entire unreceived balance of one purchase item. Purchase history
keeps the original quantity and physical receipts. The item detail shows the
cancelled quantity, reason, author and date.

| Specification cases | Executable evidence |
| --- | --- |
| `purchase-balance-C01`, `purchase-balance-C02` | [Protected HTTP tests](../../tests/backend/test_purchase_balance.py) cancel the exact unreceived amount of a partially received item. They verify the item and session history, the remaining incoming supply, the unmet Pantry demand and the ability to buy again after posting the recorded receipt. |
| `purchase-balance-C03`, `purchase-balance-C04` | Independent SQLite writers race an arrival, a duplicate key and a second cancellation. Injected failure rolls back both the cancellation and the balance change. An identical key returns its original operation across restart and activated restore, and a changed payload conflicts. |
| `purchase-balance-C05` | Native and standalone HTTP tests reject invalid reasons, stale revisions, closed balances, foreign purchase IDs, missing CSRF and absent or revoked grants. |
| `purchase-balance-C06` | The [schema 25 fixture](../../tests/fixtures/sqlite/v25-purchase-balance-source.sql), produced with `c604e25`, has prior sessions, posted and pending receipts, Pantry effects and shared-list extras. Tests cover interrupted migration, restart, preservation and restore. |
| `purchase-balance-C07` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) cancels the balance from a session item, posts the existing receipt and checks the updated shared list and reason. It uses English and Spanish in Ingress and standalone. CI runs it on amd64 and ARM64 images. |
| `purchase-balance-C08` | The same browser journey intercepts the recovery GET, checks the original session ID on the captured response, and forwards that response to the application. This avoids retrieving its body from Chromium after the workspace has refreshed. |

This increment qualifies the linked quantity correction in
`shopping-management-C17` for unreceived balances. Refunds, returns and
payments have separate acceptance.
