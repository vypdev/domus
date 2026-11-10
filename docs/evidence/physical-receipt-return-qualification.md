# Physical receipt return qualification

[Issue #86](https://github.com/vypdev/domus/issues/86) records the physical
return of one complete tracked receipt from a fully received and posted
purchase item. Shopping retains its closed purchase amounts and shows the
attributed withdrawal in receipt history.

| Specification cases | Executable evidence |
| --- | --- |
| `receipt-return-C01`, `receipt-return-C02` | [Protected HTTP and SQLite tests](../../tests/backend/test_physical_receipt_return.py) return a fractional receipt, preserve the closed purchase and other arrivals, verify the exact withdrawal and shared need, and allow an independent open purchase. A real task reservation protects the stock floor. |
| `receipt-return-C03`, `receipt-return-C04` | Independent SQLite writers race a repeated key, two returns and a correction against a return. The tests recover the same original operation, reject changed payloads and distinguish current and historical receipts after restart and activated restore. |
| `receipt-return-C05`, `receipt-return-C06` | Both protected HTTP compositions enforce both grants, current revision, scope, CSRF and receipt eligibility. An injected link failure rolls back the withdrawal and original operation. |
| `receipt-return-C07` | The [schema 28 fixture](../../tests/fixtures/sqlite/v28-physical-receipt-return-source.sql), generated with `3e60abd`, includes a session, posted and pending receipts, voids, cancellations, linked corrections and a historical Inventory reversal. Tests preserve these rows, roll back an interrupted migration, and reject an inconsistent return or withdrawal in snapshot verification. |
| `receipt-return-C08` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) returns a receipt from a closed session item, checks both histories and renewed shared need in English and Spanish, Ingress and standalone. CI executes it on amd64 and ARM64 images. |

The linked return extends the history and exact receipt invariants in
`shopping-management-R4`, `shopping-management-R5` and
`shopping-management-R6`.
