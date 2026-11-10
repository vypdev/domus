# M3 Inventory catalog and stock intake qualification

[Issue #68](https://github.com/vypdev/domus/issues/68) delivers the first
supplies increment against the [Inventory specification](../../specs/household-inventory.md).
The workspace covers a protected product catalog and positive intake at the
household's logical Pantry location. Each product has a stable identity and an
immutable base unit. New catalog registrations create a binding on the existing
stock ledger. A read transaction projects recorded, reserved and available
quantities from that ledger and its reservations.

Package conversions, location management, lots, expiry, stock corrections,
replenishment, shopping, purchase receipts and barcode lookup remain separate
increments. The original 35 Inventory cases and four Inventory recurrence
cases retain their owners and scope.

| Added acceptance cases | Executable evidence |
| --- | --- |
| `inventory1-C01` and `inventory1-C02` | [Protected HTTP tests](../../tests/backend/test_inventory_catalog_http.py) cover household and actor scope, current grants, cursor binding and stable registration. The [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) verifies navigation, empty state, registration and localized product details. |
| `inventory1-C03` and `inventory1-C04` | [SQLite integration tests](../../tests/backend/test_inventory_catalog_storage.py) observe exact attributed movements, two writers racing with the same key, separate concurrent additions, restart, and original receipt recovery. The browser journey discards a committed reply and recovers it after reloading the protected workspace. |
| `inventory1-C05` | The SQLite integration test records task-scoped consumption against a reserved catalog binding. The [retained recurrence tests](../../tests/backend/test_inventory_recurrence.py) continue to verify existing task bindings, reservations and physical movements. |
| `inventory2-C01`–`inventory2-C03` | The HTTP tests exercise all supported units, exact six-decimal stock, the whole-piece limit, rejection of zero, negative and excess-precision amounts, and closed command shapes that reject unit changes. |
| `inventory3-C01`–`inventory3-C03` | The HTTP tests reject client-selected locations. The storage tests verify the server binding and roll back a failed catalog write. Chromium verifies the Pantry label and review in both locales. |
| `inventory3-C04` | The [schema 19 fixture](../../tests/fixtures/sqlite/v19-inventory-catalog-source.sql) comes from the pre-change runtime. Migration preserves its stock ledger and reward settings. The activated checkpoint test verifies current stock and a historical intake receipt. Snapshot validation rejects a product whose persisted base unit differs from its binding. |

Application, architecture, documentation, wheel and browser evidence belong
to the reviewed source revision. The linked pull request records coverage
globally and per file, the amd64 and ARM64 image jobs, and the CI and Bugbot
results for its reviewed head. These fixtures exercise Ingress and standalone
in English and Spanish. Installed release acceptance belongs to its own gate.
