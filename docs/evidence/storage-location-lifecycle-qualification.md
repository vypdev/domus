# Storage location lifecycle qualification

Issue #90 and draft PR #183 implement the eight `stock-location-lifecycle`
cases in the [owning specification](../../specs/household-inventory.md#manage-storage-location-names-and-archived-locations).
Acceptance is in progress. This record does not claim an installed Edge result,
completed image CI, substantive review or merge.

Named locations gain a revision and archived state in schema 38. Rename,
archive and restore use the existing protected command, receipt and transaction
boundary. Archive checks every directly bound balance and live effect, including
pending task material use. General product demand without a location and settled
history do not block an empty location. Archived names and identities remain
reserved. No background cancellation or stock adjustment is implied.

| Cases | Authored verification |
|---|---|
| C01, C02 | `tests/backend/test_storage_location_lifecycle.py`: real protected commands in both HTTP compositions, duplicate and no-op names, Pantry, complete physical/effect checks and the archived 32-location capacity. |
| C03 | The same module checks current grants, original recovery and household isolation; `frontend/tests/storage-locations.test.ts` checks current controls and scope retirement. |
| C04, C05 | Independent SQLite writer races, revision conflicts, failure after the actual metadata update, original receipt replay and rollback of state/receipt/audit/outbox in the backend module. |
| C06 | Genuine schema 37, schema 30 with a real paired transfer, and schema 20 are upgraded without replacing original rows. Restart, snapshot activation and historical restore recovery are covered by the backend module and the new installed-image fixture. |
| C07 | `frontend/tests/e2e/tasks.spec.ts` adds four keyboard/touch journeys across native/standalone and English/Spanish. They retain independent drafts, lose an actual successful reply, recover its original operation and archive/restore the same identity with retained movement history. All four source journeys and the complete 177-journey application suite pass with zero retries, skips, flaky or unexpected results; actual-image execution is pending. |
| C08 | Both architecture images and the exact installed Edge candidate remain acceptance gates. No Stable deployment is authorized by this increment. |

Local interface qualification currently passes 2,321 tests with 100% lines,
statements, functions and branches globally and in all 122 authored modules.
The independent source-inventory check also passes. All 70 catalog journeys pass. The backend campaign passes 6,123 tests with 100% lines and branches globally
and in all 251 authored modules, including its independent coverage audit.
The focused compatibility campaign also passes 137 tests. These are local source results, not substitute artifact or
deployment evidence.

The schema-37 SQL fixture and provenance were captured by the unchanged installed
Edge.95 wheel, after matching all 250 installed Python modules to accepted Git
blobs and the wheel digest to its artifact manifest. The fixture includes three
locations and four real paired transfers. Its generator, SQL and provenance live
under `tests/fixtures/sqlite/`. The barcode compatibility test also replaces its
old synthetic schema-34 downgrade with a fixture upgraded by unchanged historical
schema-34 source. Both captures preserve original business rows and verify the
SQL roundtrip. Neither is manufactured by removing schema-38 fields.

Published [standalone](../contracts/household-api.openapi.json) and
[native](../contracts/native-household-api.openapi.json) contracts include the
three strict lifecycle commands, string revisions, archive preconditions and
archived history rows. Original add-location receipts keep their existing two
fields; lifecycle receipts have only identity, name, revision and archived state.

The native Copilot SDD verification could not find its original publication
evidence after the earlier branch-admission failure. The owning SDD and branch
recovery were explicitly authorized; the diagnostic is recorded in
[Copilot #1005](https://github.com/vypdev/copilot/issues/1005#issuecomment-7241629733).
This exception does not remove product CI, review, migration or Edge gates.
