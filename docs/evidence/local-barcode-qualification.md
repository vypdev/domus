# Local barcode qualification

Issue #91 adds manual product lookup and reviewed local associations in Inventory.
The selected companion defines five requirements and eight acceptance cases.
[Local barcode specification](../../specs/stock-local-barcode.md)

Printed ASCII GTIN-8, GTIN-12, GTIN-13 and GTIN-14 values retain leading zeroes.
Validation checks the original length and GS1 check digit before zero-padding the
identity to 14 characters. The household and canonical code identify one current
association. Every link receives a fresh association ID. Removal matches that
reviewed identity, including when a later link selects the same product.

Inventory uses the shared ha-ui numeric text field, cards, buttons and feedback
from the exact published version `0.1.0-next.3`.
The field preserves malformed input for correction. An unlinked result leads to
the existing paginated Pantry cards. A manager chooses a product, reviews its name
and code, then separately confirms. A found product opens its existing stock
detail. An unavailable read retains the draft and offers an explicit retry.

Association writes use the existing atomic commands, journal, original receipts,
current grants, CSRF and origin checks. A lost successful response recovers its
original operation. Rejected stale removal refreshes the current match and retires
the old confirmation. Scope changes retire private facts and drafts.

| Published case | Executable evidence |
| --- | --- |
| stock-local-barcode-C01 | Domain and client tests validate all four lengths, original shape, check digits and equivalent canonical forms. [Backend cases](../../tests/backend/test_inventory_barcodes.py), [client cases](../../frontend/tests/inventory.test.ts) |
| stock-local-barcode-C02 | Exact current-household queries distinguish found and unlinked codes. Compiled journeys abort external requests and complete both local flows. [HTTP cases](../../tests/backend/test_inventory_barcode_http.py), [compiled journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts) |
| stock-local-barcode-C03 | Both HTTP compositions check current readers, management grants, foreign households and original receipt authority. Component tests retire management controls after current grants change. [HTTP cases](../../tests/backend/test_inventory_barcode_http.py), [component cases](../../frontend/tests/inventory.test.ts) |
| stock-local-barcode-C04 | Two real SQLite writers race equivalent forms for different products. One wins. Stale removal preserves a replacement association, including a new link to the same product. Two browser tabs verify conflict recovery after reassignment to another product. [SQLite cases](../../tests/backend/test_inventory_barcodes.py), [compiled journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts) |
| stock-local-barcode-C05 | Original replay preserves the operation and rejects a changed payload. Late receipt failure rolls back association changes. Compiled journeys commit a link, lose its response, reload and recover the same original request. [SQLite cases](../../tests/backend/test_inventory_barcodes.py), [compiled journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts) |
| stock-local-barcode-C06 | Schema 34, 30 and 20 data survive migration to 35. Invalid migration SQL leaves source bytes unchanged. Checkpoint activation preserves the link and its original receipt. Snapshot validation rejects corrupted barcode and association identities. [Migration and restoration cases](../../tests/backend/test_inventory_barcodes.py) |
| stock-local-barcode-C07 | Ingress and standalone journeys exercise English desktop keyboard, Spanish 390 px touch, light and dark themes, focus, malformed input, selection, confirmation, current conflicts and explicit read retry. [Compiled journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts) |
| stock-local-barcode-C08 | The immutable Edge candidate requires both CPU image campaigns and installed-owner acceptance. The increment's pull request records their measured source identities and outcomes. |

The complete backend campaign passes 5,569 tests with 100% statement and branch
coverage globally and across all 231 authored modules. An independent source
coverage audit accepts the report. The complete frontend campaign passes 1,927
tests with all four metrics at 100% globally and per authored runtime file.
All 121 compiled source journeys and 45 rebuilt catalog journeys pass, with zero
skipped, unexpected or flaky results. The CPU image gate requires all 66 household
journeys on each architecture, including the two new barcode journeys.

SQLite schema 35 adds the local association index. Keep the previous compatible
image together with its cold schema-34 state for rollback. Compatible schema-35
restoration retains current associations and original historical evidence.
