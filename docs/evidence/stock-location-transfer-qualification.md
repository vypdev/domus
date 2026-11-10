# Storage location and stock transfer qualification

[Issue #88](https://github.com/vypdev/domus/issues/88) covers named storage
locations, exact transfers and product balances by location. It exercises the
balanced-transfer and location portions of the Inventory contract.

| Specification cases | Evidence |
| --- | --- |
| `stock-location-transfer-C01`, `stock-location-transfer-C05` | [Protected HTTP tests](../../tests/backend/test_stock_transfers.py) exercise current grants, location identity, duplicate names, household reads, CSRF and operation recovery in both compositions. |
| `stock-location-transfer-C02`, `stock-location-transfer-C03` | The same suite checks signed movements, stock totals, Pantry need, exact quantities, reservation floors, destination capacity and rollback after the first leg. |
| `stock-location-transfer-C04`, `stock-location-transfer-C07` | Independent SQLite connections race the original key and competing transfers. Restart and activated restore preserve current and historical receipts. |
| `stock-location-transfer-C06` | The schema 29 [source fixture](../../tests/fixtures/sqlite/v29-stock-location-source.sql) was generated from `3d03725` with an existing physical return. The migration suite also uses the representative schema 20 fixture and verifies transaction rollback, historical identities and transfer linkage. |
| `stock-location-transfer-C08` | The [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) exercises desktop keyboard use in English and narrow touch use in Spanish. Image CI and the installed Edge candidate are separate evidence. |

Shopping intake, adjustments and replenishment use the Pantry binding.
The transfer records identify both physical locations and retain the
original command result across retries.
