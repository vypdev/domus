# Overview stock attention qualification

[Issue #102](https://github.com/vypdev/domus/issues/102) adds an Overview summary
for products whose available stock falls below the configured replenishment minimum.
The protected read uses one household snapshot and preserves the existing storage schema.

| Published case | Executable evidence |
| --- | --- |
| `overview-stock-C01` | The [stock summary HTTP tests](../../tests/backend/test_stock_attention.py) compare exact stock below, equal to and above the minimum, including a material reservation and an outstanding purchase. Repeated reads preserve stock, reservations and purchase balances. |
| `overview-stock-C02` | The same tests check the exact total across multiple catalog pages, the first 25 qualifying product IDs, fractional units and a successful empty response. |
| `overview-stock-C03` | Both HTTP compositions deny access after household read authority is revoked. A Pantry reader without Tasks read authority retains access to the stock summary. |
| `overview-stock-C04` | The [transport and component tests](../../frontend/tests/stock-attention.test.ts) reject malformed projections. The [workspace tests](../../frontend/tests/page.test.ts) check independent stock and task states, retry and verified context changes. |
| `overview-stock-C05` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) checks English desktop keyboard and narrow Spanish touch navigation to Inventory. It checks focus, the localized intake review and removal from Overview when stock reaches the minimum. |
| `overview-stock-C06` | The exact Edge candidate runs in the amd64 and ARM64 image checks. Installed acceptance checks the stock summary in a disposable Home Assistant instance and records removal of the instance and its repository source in the pull request. |
