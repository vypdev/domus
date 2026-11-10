# Purchase session qualification

[Issue #78](https://github.com/vypdev/domus/issues/78) records one shopping trip
from two to sixteen selected rows in the shared list. History groups existing
purchase items by shopper and time. The item view retains separate bought,
received, due and pending Pantry quantities.

| Specification cases | Executable evidence |
| --- | --- |
| `purchase-session-C01`, `purchase-session-C04`, `purchase-session-C06` | The [protected HTTP tests](../../tests/backend/test_purchase_sessions.py) cover ordering and attribution, exact tracked and untracked quantities, rejected selections, current grants, CSRF and signed history pages in both deployment compositions. |
| `purchase-session-C02`, `purchase-session-C03` | Real SQLite writers race duplicate keys, competing sessions and a competing individual purchase. A losing operation leaves no partial group. Identical retries recover the same group and item IDs, while a changed payload conflicts. |
| `purchase-session-C05` | The HTTP cases receive a tracked item in part, complete an untracked receipt and post the tracked receipt. Session detail shows the four independent amounts. |
| `purchase-session-C07` | The [schema 24 fixture](../../tests/fixtures/sqlite/v24-purchase-session-source.sql) carries Pantry effects, individual purchases, posted and pending physical receipts and active and cleared extras from the `ed41596` runtime. Tests cover interrupted migration rollback, preservation, reopening and activated restore with historical and current receipts. |
| `purchase-session-C08` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) selects items from the shared list, reviews exact quantities, recovers a lost session response, and receives and posts a tracked item. It exercises English and Spanish in Ingress and standalone. CI runs it on both actual image architectures. |

This qualifies `shopping-management-C16` and `shopping-management-C18`, and
rechecks purchase, receipt, permission and original-operation invariants for
grouped items.
