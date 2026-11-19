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
A submitted search continues keyboard focus to its result or retry control once
the read finishes. A current view owns that continuation and preserves focus
that the user has moved elsewhere.

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
coverage audit accepts the report. The complete frontend campaign passes 1,929
tests with all four metrics at 100% globally and per authored runtime file.
All 121 compiled source journeys and 45 rebuilt catalog journeys pass, with zero
skipped, unexpected or flaky results. The CPU image gate requires all 66 household
journeys on each architecture, including the two new barcode journeys.

SQLite schema 35 adds the local association index. Keep the previous compatible
image together with its cold schema-34 state for rollback. Compatible schema-35
restoration retains current associations and original historical evidence.

## Edge.52 observation

Edge.52 packages runtime source `3751c4e1650f5de5433bcbefe228260c0b07753b`.
The source archive SHA-256 is
`db5d9e29761e7ab22e79bd04c51e6d4e26eac73a303eeb8c64cdaa330b0fcb9d`.
The independently measured Linux wheel SHA-256 is
`2038b6218c8b2f5371e4cd5797a03af1274b9de8c17b698a69e3d59bb5969975`.
All 231 Python modules match Git, the wheel and the installed Linux builder.
The four compiled UI files match the local and Linux builds, and the normal
local wheel matches the Linux wheel exactly. The artifact declaration records
those measured bytes. [Edge artifact](../../addon-edge/artifact.json)

Both CPU image campaigns, installed-owner acceptance and final same-head CI
and review are tracked in the increment's pull request. [PR #145](https://github.com/vypdev/domus/pull/145)

## Installed keyboard correction

The installed Edge.52 candidate reproduced loss of keyboard focus after a
successful lookup. Its disabled input relinquished focus to the document body.
Edge.53 carries the correction and requires repeated installed acceptance. The regression
checks found and unlinked results, unavailable retry, retained input, moved focus,
background documents and retired view ownership. Both compiled barcode journeys
require result focus and use the real next Tab to reach product selection.

## Immutable Edge.53 candidate

Edge.53 packages runtime source `465f780ee37275471a32238fafe7dfb5866dd478`.
The source archive SHA-256 is
`7d9bc569a0cdb962ad205037eea159cc7bbe3317aa03a00454b83bf00c4839e4`.
The independently measured Linux wheel SHA-256 is
`7a47e346cc62887c02b501ce93a0f0c94e01e2c627e3bd838aaac02e0bddbae2`.
All 231 Python modules match Git, the wheel and the installed Linux builder.
The four compiled UI files match the local and Linux builds. The normal local
wheel matches the Linux wheel exactly. Schema 35 is retained.
The actual-owner update, both CPU image campaigns and final same-head CI and
review are tracked in the increment's pull request.

## Confirmed write continuation

Installed Edge.53 retains the household, products and association from Edge.52.
English keyboard query continuation, real Tab navigation, cancelled review,
two-tab stale removal and Spanish 390 px touch passed. A temporary offline read
focused its explicit retry and retained all entered digits. Returning that tab
to the network and retrying restored the current match.

A confirmed removal then relinquished focus to the document body. Edge.54 will
also continue focus after confirmed association writes and rejected stale removal,
waiting for the refreshed current result. An unconfirmed barcode write continues
to its original-request recovery control. Its regression covers accepted links,
accepted removals and an intermediate obsolete view during conflict refresh.

The Edge.53 package-head frontend campaign also exposed an unrelated fixture
ordering race. Opening the selected automation draft read its execution state
while the test immediately seeded stock and history through independent writes.
The preserved trace reports a 503 `storage_busy` for that execution read and the
interface offers its explicit retry. The test now waits for the current rule
control before seeding later history. The existing write-concurrency and
unavailable-read acceptance cases retain their original assertions.

A complete local campaign reached its 600-second suite deadline after 113 passing
cases. Its assignment fixture also chose Spanish before reloaded preferences
finished hydrating, then waited for a Spanish recovery control while the interface
was in English. The fixture now waits for the loaded Tasks heading before choosing
the locale. Assignment journeys use the existing progress journey's 75-second
bound, and the complete 121-case suite has a 900-second bound for shared runners.
All case assertions and the zero-retry policy remain applicable.

The static catalog server uses HTTP/1.1 persistent connections. Two earlier local
catalog campaigns lost JavaScript resource connections before their stories
loaded. Their original traces are retained. With HTTP/1.1, all 45 cases pass in
two consecutive zero-retry campaigns. Barcode recovery now waits for the restored
product projection and a valid captured original request key before reading the
receipt. Both deployment journeys pass twice with the recovery focus assertion.
