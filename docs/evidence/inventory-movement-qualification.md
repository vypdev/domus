# M3 Inventory movement history and stock correction qualification

[Issue #70](https://github.com/vypdev/domus/issues/70) extends the protected
Pantry catalog. The same ledger exposes attributed intake, task consumption,
task corrections, manual adjustments and linked intake reversals. Manual
commands and original receipts use the existing transactional writer.
An intake reversal removes the full original amount once, subject to stock
available after active reservations. Task regularization stays in Tasks.

| Specification cases | Executable evidence |
| --- | --- |
| `inventory-movements-C01`, `inventory-movements-C02` | [Protected HTTP history](../../tests/backend/test_inventory_catalog_http.py) checks current household permission, scoped cursors, attribution, bounds and stable pages when later entries arrive. The [migration and restore tests](../../tests/backend/test_inventory_movements.py) verify existing task sources and links. |
| `inventory-movements-C03`, `inventory-movements-C04` | The HTTP and SQLite tests check both adjustment signs, exact unit precision, reason, viewer denial, immutable original entries and rejection of a task movement as an intake reversal target. |
| `inventory-movements-C05`, `inventory-movements-C06` | The SQLite tests check an active reservation, excessive removal, failure after append, concurrent independent writers with shared and distinct keys, and recovery of the same original receipt after reopening storage. |
| `inventory-movements-C07` | The [schema 20 fixture](../../tests/fixtures/sqlite/v20-inventory-history-source.sql) comes from `eab3077`. The migration test verifies rollback, original movement positions and links, task consumption, exact balances, active reservations and receipts. Activated restoration distinguishes current and historical correction receipts. |
| `inventory-movements-C08` | The [compiled Chromium journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) inspects signed history in both locales and deployments, recovers a lost reversal reply after reload, verifies both links, and records a signed adjustment. The PR records current CI and actual-image results on amd64 and ARM64. |

This evidence covers the original Inventory cases `C04` (attributed adjustment),
`C05` (no deletion path), `C06` (linked compensation), `C22` (viewer denial),
`C23` (reconciled restoration) and the pagination portion of `C24`. The existing
Inventory and Tasks tests retain their ownership of task material cases.
See the [owning specification](../../specs/household-inventory.md).
