# Manual shopping annotation qualification

[Issue #157](https://github.com/vypdev/domus/issues/157) implements the bounded
[companion contract](../../specs/shopping-manual-annotations.md) under the
retained Shopping owner. This record distinguishes executed source checks
from publication, compiled images and installed acceptance still pending.

Current checkpoint: the schema-37 backend, annotated reads/recovery and complete
note/priority form pass their source checks. All five `0.1.0-next.5` packages
were published through [ha-ui #44](https://github.com/vypdev/ha-ui/pull/44).
Domus pins that exact public core version and its lockfile; all 172 installed
package files match the independently downloaded public tarball. The
[machine-readable qualification](shopping-manual-annotations.json) records
the compiled source bytes and separates the pending immutable package,
CPU-image and installed acceptance gates.

The installed Edge.73 baseline rejects and retains a 1,001-character note with
focus returned to the field, then saves a literal multiline/tab/emoji note with
Urgent priority and unchanged zero stock. Visual review also found that the
priority label's named font had no generic fallback. The correction scopes the
published font token to the two annotation controls, matching Domus's existing
body font stack. Its actual catalog regression failed before the correction;
all 2,164 frontend tests and 68 catalog cases pass afterward. The previous
73 bytes and observations remain historical in the JSON record. Current full
entry, immutable Edge.74 and installed upgrade acceptance remain pending.

| Native case | Evidence and current outcome |
| --- | --- |
| `shopping-manual-annotations-C01` | The [domain/storage tests](../../tests/backend/test_shopping_annotations.py), [both protected HTTP compositions](../../tests/backend/test_shopping_annotations_http.py) and [client contracts](../../frontend/tests/shopping-annotations.test.ts) exercise empty/omitted defaults, all four priorities, exact quantities, 1,000 supplementary characters, literal CR/LF/tab and prohibited controls. The four [compiled HTTP journeys](../../frontend/tests/e2e/shopping-annotations.spec.ts) pass with actual note entry, native Enter, correction, literal HTML text, supplementary characters and independent requests. Installed acceptance remains pending. |
| `shopping-manual-annotations-C02` | Strict annotated read tests retain independent manual-source identities and annotations, with `null` for automatic and aggregate entries. A 25-note page of 1,000 supplementary characters per note passes its bounded read budget. Source component checks verify independent literal notes and textual priorities in English and Spanish; installed display remains pending. |
| `shopping-manual-annotations-C03` | Both HTTP compositions exercise current request/read/task-detail grants, cross-household denial and separately bound legacy/annotated cursors. Existing client HTTP, roster and page-navigation regressions pass. |
| `shopping-manual-annotations-C04` | The exact public next.5 selector and textarea supply localized labels, defaults, controlled values and field errors. All 68 cases across the 45-story catalog pass, including eight shopping examples in both modes/locales, real keyboard submission and 390 px touch in both themes. Error, help and entered-text contrast is measured at least 4.5:1. Actual invalid-note correction returns focus to the field. The four protected HTTP journeys also pass at 390 px with touch enabled. Installed acceptance remains pending. |
| `shopping-manual-annotations-C05` | The [actual Edge.72 journal/controller fixture](../../frontend/tests/fixtures/edge72-inventory-journal.provenance.json) preserves exact legacy packets and refuses new annotated pending data without sending or deleting it. Cold re-upgrade recovers original committed, historical and missing outcomes with the same key/command. Form ownership regressions include note and priority edits and preserve later drafts after edits, form/scope changes and historical/rejected outcomes; temporary disabled state does not change the entered-value fingerprint. Four real HTTP journeys lose a committed reply, reload and recover the original operation without another POST. |
| `shopping-manual-annotations-C06` | Original-key replay returns the original result; changing explicit note or priority conflicts without creating another extra. Omitted annotation fields preserve the legacy fingerprint. |
| `shopping-manual-annotations-C07` | Independent writers race duplicate and changed requests. Failures after extra, receipt, audit and outbox writes roll back the entire operation; retry then commits once. Quantities, stock and purchase facts retain their original semantics. |
| `shopping-manual-annotations-C08` | The [genuine schema-36 fixture](../../tests/fixtures/sqlite/v36-shopping-annotations-source.provenance.json) was captured through the actual previous runtime before the schema changed. Focused schema-36/schema-20 migration, failed second ALTER, reopen, actual snapshot activation and historical receipt tests pass. Final candidate/image compatible rollback remains pending. |
| `shopping-manual-annotations-C09` | The companion retains its eight native requirement IDs, ten case IDs and reciprocal ownership. API snapshots describe the additive annotated wrappers; legacy response shapes remain unchanged. The retained catalog SDK regenerated and validated the actual view for all eleven capabilities. Final candidate-linked qualification remains pending. |
| `shopping-manual-annotations-C10` | Frontend after the typography correction: 2,164 tests pass with 100% global/per-file coverage across all four metrics and all 119 runtime files; the 68 catalog cases pass. The unchanged backend has 5,919 source tests with 100% statement/branch coverage globally and per file across all 250 runtime modules. The 42 Node policy tests, 187 tooling tests and 51 Python architecture checks pass. The prior Edge.73 source passed all 129 protected compiled entry cases, with zero skipped, unexpected, flaky or retried cases, and all ten static package contracts plus its actual wheel bundle/license check. Its public archive matched all 1,018 Git blobs and all 250 wheel runtime files. Its local ARM64 image passed nine byte, migration, restart, restoration, rollback and listener cases. Current complete entry execution remains required in final-head CI; the local repeat stopped before any case because an active Actions image fixture owned its ports. Immutable Edge.74, both final CPU campaigns, installed acceptance and scoped cleanup remain pending. Distribution and Stable are outside this increment. |

The original failed draft regressions demonstrated that an earlier outcome
could reset another form. The correction binds a submission to its scope,
form identity, input revision and exact form fingerprint. Only its unchanged
current draft clears on a committed result. Historical and rejected outcomes
retire that ownership while retaining the entered values.

Actual mobile touch exposed a second issue: showing a field error only on blur
moved the Save button between pointer-down and click. Live domain validation
now displays the error while editing. Both palette/locale touch regressions
pass without retries, and the full source and catalog campaigns were rerun.

The frozen previous client derives from accepted source
`31553dda1f3782b916c16b13818154cdc66ec520`, with all 120 previous frontend
source files compared against merge `0cdc633e3d4bb374f31277cb4861fbe13de9b9ea`.
Its accepted wheel digest is recorded independently in the fixture provenance.
This fixture proves the client journal/controller boundary; it does not claim
whole-application image rollback or native Home Assistant acceptance.

The container qualification fixture now preserves every original column from the
frozen schema-20 and schema-36 inputs, reopens the same annotated command in a
fresh interpreter, activates an actual checkpoint and verifies the historical
clear outcome. Both input cases have passed against the current host source;
execution inside both CPU candidates remains pending. The exact accepted
Edge.72 Dockerfile is retained in `tests/fixtures/schema36-app/Dockerfile` for
the separate compatible-binary/private-checkpoint rollback. CI requires that
image in both CPU jobs and retires its owned tag after the job.
