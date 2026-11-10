# Pantry replenishment qualification

[Issue #72](https://github.com/vypdev/domus/issues/72) adds a versioned minimum
and target for each Pantry product. The protected Inventory read projects one
exact replenishment quantity from the policy, ledger balance and active
reservations. The product remains the source through repeated evaluation,
satisfaction and reopening. Inventory managers save the policy through the
existing transactional command and original receipt flow.

| Specification cases | Executable evidence |
| --- | --- |
| `pantry-replenishment-C01`, `pantry-replenishment-C02` | The [protected HTTP tests](../../tests/backend/test_inventory_catalog_http.py) cover current household and management permissions, original receipt access, CSRF, exact decimal bounds, fractional pieces and rejected inputs in both HTTP compositions. |
| `pantry-replenishment-C03`, `pantry-replenishment-C04` | The [SQLite tests](../../tests/backend/test_pantry_replenishment.py) cover the exact fractional gap, equality with the minimum, reopening, disabling and preservation of task demand, active reservations and pending consumption across intake and reevaluation. |
| `pantry-replenishment-C05` | The SQLite tests race independent writers with shared and distinct keys, replay after reopening storage, reject a changed payload and inject a failure after the policy write to prove rollback. |
| `pantry-replenishment-C06` | The [schema 21 fixture](../../tests/fixtures/sqlite/v21-pantry-replenishment-source.sql) was produced by the runtime merged at `e05958fd4df855cb24449372151135e361eba650`. Migration preserves task consumption, active reservations, intake and correction links, and original receipts. An injected migration failure leaves the source database unchanged. |
| `pantry-replenishment-C07` | The SQLite tests activate a compatible snapshot, recover the exact settings and projected source, and distinguish current from historical receipts. Fractional piece policies are rejected when verifying a damaged snapshot. |
| `pantry-replenishment-C08` | The [compiled Chromium journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) edits and displays thresholds in English and Spanish under Ingress and standalone, recovers an original reply after reload, and checks equality with the minimum. CI runs this journey against the amd64 and ARM64 images. |

This qualifies the Pantry portions of `household-inventory-C10`,
`household-inventory-C11` and `household-inventory-C34`. Shopping and the
manual extra demand contract in `household-inventory-C12` remain separate.
See the [owning specification](../../specs/household-inventory.md).
