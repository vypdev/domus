# Shopping purchases and receipt qualification

[Issue #74](https://github.com/vypdev/domus/issues/74) covers the first purchase
and receiving slice of [Shopping Management](../../specs/shopping-management.md).
The protected Shopping card in Inventory records one-item purchases, exact
physical arrivals and separate Pantry postings. Purchase and arrival history
retains its actor, date, quantities and stock movement link.

| Specification cases | Executable evidence |
| --- | --- |
| `shopping-receipts-C01`, `shopping-receipts-C02` | The [HTTP tests](../../tests/backend/test_shopping_http.py) record a fractional tracked purchase and partial arrival in both deployments, verify exact posting and outstanding amounts, and receive an untracked item without a catalog or ledger record. |
| `shopping-receipts-C03`, `shopping-receipts-C04` | The [SQLite tests](../../tests/backend/test_shopping_storage.py) race independent connections, replay original commands and inject an interruption after ledger append. The durable physical receipt survives capacity rejection and an interrupted posting. |
| `shopping-receipts-C05` | The SQLite migration and restore journey checks the amount still to buy before and after posting compatible supply. The [task integration test](../../tests/backend/test_pantry_replenishment.py) preserves active reservations, task demand and pending regularization when a purchase receipt is posted. |
| `shopping-receipts-C06` | The HTTP tests check scope, CSRF, viewer denial, independent shopping and posting grants, and revoked authority on original receipt recovery. |
| `shopping-receipts-C07` | The [schema 22 fixture](../../tests/fixtures/sqlite/v22-shopping-source.sql) uses the runtime at `1c88bb4ee84771644b2135efcbeb5755c9538830`. Tests check transaction rollback and preservation of products, policies, movements, task reservations and receipts during migration. |
| `shopping-receipts-C08` | The SQLite tests reopen storage, activate a snapshot containing pending and posted receipts, and recover original and historical outcomes. Snapshot validation detects inconsistent quantities, revisions and movement links. |
| `shopping-receipts-C09` | The [Chromium workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) exercises a partial receipt, a lost posting response and original recovery in both locales and deployments. CI runs the journey in both actual images. |

The scope qualifies the purchase and receiving parts of
`shopping-management-C10`, `shopping-management-C11`, `shopping-management-C12`,
`shopping-management-C13`, `shopping-management-C14`, `shopping-management-C15`,
`shopping-management-C18`, `shopping-management-C19` and `shopping-management-C21`.
Multi-list demand planning, manual extra consolidation, task demand allocation,
purchase sessions, pricing and refunds have separate acceptance.
