# Purchase session store qualification

[Issue #94](https://github.com/vypdev/domus/issues/94) adds an optional store
name to a purchase session. A shopper can review the name and quantities
together and find the store in the saved trip.

| Published case | Executable evidence |
| --- | --- |
| `purchase-session-store-C01` | The [protected HTTP cases](../../tests/backend/test_purchase_sessions.py) record named and unnamed trips and reject blank, control-character and overlong store names without a session or original receipt. The [component tests](../../frontend/tests/inventory.test.ts) keep invalid text available for correction and check the 160-character Unicode bound. |
| `purchase-session-store-C02` | Both compositions return the name with the saved shopper and items under current Shopping read authority. The HTTP cases check unauthorized access and retain independent purchase, arrival and Pantry quantities. |
| `purchase-session-store-C03` | The HTTP cases replay the exact named receipt and reject a changed store under the same key. The previous schema fixture recovers an unnamed original with the same inputs. The [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) loses the named response and recovers it with the original key. |
| `purchase-session-store-C04` | The SQLite cases inject a late failure after the session and item rows are written and race competing named sessions. Only a committed winner leaves a session, its items and a receipt. |
| `purchase-session-store-C05` | Tests migrate the [schema 30 fixture](../../tests/fixtures/sqlite/v30-purchase-store-source.sql) with an unnamed session, stock transfer and posted return and the [schema 20 fixture](../../tests/fixtures/sqlite/v20-inventory-history-source.sql) with historical Pantry records. They check byte-identical rollback on migration failure, reopen the database and activate a compatible backup containing a named session and its original receipt. |
| `purchase-session-store-C06` | The compiled journey corrects store and quantity errors with the Spanish form at 320 pixels, records with English desktop keyboard input and verifies the saved store in both languages. Image CI runs the journey on amd64 and ARM64 in Ingress and standalone. |

The schema 31 migration adds a nullable store column. Keep a stopped
application backup before upgrading an existing instance. The older image
needs that backup to reopen its prior database.
