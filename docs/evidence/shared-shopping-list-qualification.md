# Shared shopping list qualification

[Issue #76](https://github.com/vypdev/domus/issues/76) adds one protected list in
Shopping within Inventory. Product identity and base unit determine tracked
groups. Pantry, Tasks and manual extras retain their individual sources.
Free-text extras remain independent.

| Specification cases | Executable evidence |
| --- | --- |
| `shared-shopping-C01`, `shared-shopping-C02` | The [projection tests](../../tests/backend/test_shared_shopping.py) verify four Pantry units plus two manual units, with zero additional demand for a fully reserved task. They also verify exact allocation of unreserved stock and incoming supply across independent task shortages. |
| `shared-shopping-C03`, `shared-shopping-C04` | The HTTP tests in both deployments retain same-name extras separately, reject fractional pieces and foreign products, expose stable Task material identities, and remove completed work from current demand. |
| `shared-shopping-C05`, `shared-shopping-C06` | Independent SQLite connections race clears and replay original commands. Protected HTTP tests check request and manager grants, CSRF, current access on recovery, and signed cursors bound to the member and product. |
| `shared-shopping-C07` | The [schema 23 fixture](../../tests/fixtures/sqlite/v23-shared-shopping-source.sql) contains data from `d8840e4acd61425622f2dc7f571ef0adc9092687`. Migration tests retain Pantry policy, movements, effects, purchases, pending and posted receipts, and original operations. Injected migration failure rolls back. |
| `shared-shopping-C08` | Activated restoration reopens storage and preserves attributed extras. Committed and historical command receipts are distinct. Snapshot checks reject malformed quantities and product bindings. |
| `shared-shopping-C09` | The [workspace browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) inspects exact Pantry and Task coverage, adds an extra after a lost response, recovers the original, and clears the extra. It runs in English and Spanish in Ingress and standalone. CI runs the journey against both amd64 and ARM64 images. |

This qualifies `shopping-management-C04` through `shopping-management-C08`
and the reservation and supply coverage portions of `shopping-management-C09`.
Multiple lists, optional manual overlap, purchase allocation to individual
sources, prices, sessions and conversions have separate acceptance.
