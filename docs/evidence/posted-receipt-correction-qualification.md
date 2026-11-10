# Posted physical receipt correction qualification

[Issue #84](https://github.com/vypdev/domus/issues/84) links one full correction
of a tracked physical receipt to its compensating Pantry movement. The
original receipt and posting remain visible alongside the correction.

| Specification cases | Executable evidence |
| --- | --- |
| `posted-receipt-C01`, `posted-receipt-C02` | [Protected HTTP and SQLite tests](../../tests/backend/test_posted_receipt_correction.py) reverse an exact fractional amount, update the balance and both histories, preserve other arrivals, and post the corrected receipt. A representative task reservation prevents a decrease below reserved stock. |
| `posted-receipt-C03`, `posted-receipt-C04` | Independent SQLite writers race corrections, a repeated key, and a replacement purchase. Tests recover the original receipt, reject changed payloads, and distinguish current and historical operations after restart and activated restore. |
| `posted-receipt-C05`, `posted-receipt-C06` | Both protected HTTP compositions enforce both current grants, CSRF, revision, identity and eligibility. An injected failure after appending to the ledger rolls back the link, movement and purchase balance. |
| `posted-receipt-C07` | The [schema 27 fixture](../../tests/fixtures/sqlite/v27-posted-receipt-correction-source.sql) was generated with the runtime at `4ebedb4`. Migration tests preserve a session, pending and posted receipts, a void, a balance cancellation and an Inventory-only reversal. A historical reversal remains visible and returns its original receipt. New Shopping corrections use the linked operation. |
| `posted-receipt-C08` | Snapshot verification rejects a compensation linked to the wrong or unposted receipt and reconciles effective receipt totals and revisions. |
| `posted-receipt-C09` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) corrects a posted session receipt, checks the original and compensating Pantry movements and posts the right amount. It exercises English and Spanish in Ingress and standalone. CI runs it on both actual image architectures. |

This increment qualifies the posted physical receipt correction in
`shopping-management-C17`.
