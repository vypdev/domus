# Pending physical receipt void qualification

[Issue #82](https://github.com/vypdev/domus/issues/82) lets a shopping manager
void a tracked purchase receipt before Pantry posting. The original quantity,
shopper and timestamp stay in history alongside the reason, shopper and time
of the void.

| Specification cases | Executable evidence |
| --- | --- |
| `receipt-void-C01`, `receipt-void-C02` | [Protected HTTP tests](../../tests/backend/test_physical_receipt_void.py) void an exact fractional receipt, verify the revised balance and paginated history, and preserve other receipts, Pantry stock and incoming supply. They then receive and post a corrected amount. |
| `receipt-void-C03`, `receipt-void-C04` | Independent SQLite writers race posting and voiding, and race duplicate and competing voids. The tests recover the original operation, detect a changed payload, and distinguish current and historical results after restart and activated restore. |
| `receipt-void-C05`, `receipt-void-C06` | Both HTTP compositions enforce current grants, CSRF, exact revision, receipt ownership and eligibility. An injected failure rolls back the receipt balance, void and original operation. |
| `receipt-void-C07` | The [schema 26 fixture](../../tests/fixtures/sqlite/v26-physical-receipt-void-source.sql) was generated with the runtime at `f067b5c`. Migration tests preserve existing sessions, posted and pending receipts, balance cancellations, stock effects and operation receipts. Snapshot tests reject a void on an ineligible receipt or with an invalid reason. |
| `receipt-void-C08` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) voids a mistaken receipt from a session, records and posts the corrected amount, and verifies localized history in Ingress and standalone. CI runs it on the amd64 and ARM64 images. |

This increment qualifies the correction of a pending physical receipt in
`shopping-management-C17`.
