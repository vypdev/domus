# Task material workflow qualification (#150)

Status: implementation and qualification in progress. No complete acceptance, installed Edge result or merge is claimed here yet.

## Scope and preserved contracts

The [owning specification](../../specs/household-tasks.md) retains its original case identities and adds `task-material-planning-C01` through `task-material-planning-C12`. This increment connects optional Pantry material plans to ordinary, fixed and relative task creation, authoritative per-line outcomes, explicit settlement and the first recording of a previously missing actual quantity. Inventory remains the only stock authority. There is no new material policy editor or UI to initiate corrections of already posted usage.

The native Action published SDD commit `1e1a25e5076661a6dd2e368cad153100fb4c04e8` from accepted base `72cb687f429dc93ee6e123a3a929d60b7f69aa7e` on its managed feature ref. The preceding owner document was preserved verbatim. The full selected artifact SHA-256 was `a75b3d67dad70e1c14032a51a77f3baa42407b63b631ea2b013c05d890e33c02`.

## Evidence recorded so far

- A real native HTTP regression reproduced scheduled material creation returning 422 before the DTO mapping changed. The shared scheduled services were already wired to the Inventory binding adapter.
- The directed native and standalone HTTP/material suites passed 313 tests after adding scheduled selection mapping, the current material-linking hint, pending-settlement hints and original settlement GET support.
- Nineteen new browser component/application tests passed for bounded selection, exact zero/decimal entries, 32 distinct references, late result retirement, permission loss, current review, published ha-ui controls and per-line results.
- The existing five directed Tasks frontend suites passed 382 tests. Expanded HTTP/controller coverage subsequently passed 170 tests, including current intent revisions, frozen material-bearing originals, explicit zero recording, granular denial and recovery without a second POST.
- The complete backend suite passed 5,625 tests with all 231 runtime modules at 100% statement and branch coverage (18,020 statements and 4,870 branches). The independent backend coverage gate passed. No SQLite schema change was introduced.
- All 48 scheduled-creation HTTP cases pass, including four initial/successor material qualifications across both compositions, also included in the whole-backend campaign. Exact material-line identities, binding and quantities survive materialization; replaying completion and successor generation does not duplicate consumption. Explicit zero leaves the original completed cycle's unused intent and no stock movement.
- The complete frontend suite passed 2,016 tests in 44 files. All 110 authored runtime files and all four metrics are 100%: 8,701 statements, 7,803 branches, 1,888 functions and 6,327 lines. The independent source-inventory and compatibility-fixture identity checks passed. Thresholds remain unchanged.
- The initial four-source-journey campaign passed three combinations and exposed a long-select scrolling defect in standalone Spanish touch with `@vypdev/ha-ui@0.1.0-next.3`. [ha-ui #39](https://github.com/vypdev/ha-ui/issues/39) owns the shared correction, merged through PRs #40 and #41 and published as the complete five-coordinate `0.1.0-next.4` cohort. The approved production archives and independently downloaded registry bytes match. OIDC publication run `44699421594`, attempt 6, succeeds after the documented partial-publication recovery while each version propagated.
- Domus pins the published `0.1.0-next.4` in its manifest and frozen lock. The physically installed select renderer matches its verified tarball. Types, all 2,016 frontend tests, the independent coverage/fixture checks and all four coverage metrics pass again. The rebuilt server wheel contains the exact four newly compiled UI assets.
- The complete consumer campaign passes all 125 entry journeys and all 46 catalog cases, with zero skipped, flaky or unexpected cases. All four material workflows pass: native and standalone, English keyboard and 390 px Spanish touch. They cover ordinary/fixed/relative plans, posted/unused/shortfall outcomes, explicit settlement and missing quantities, retained drafts, lost replies and original GET recovery. The select is exercised through real input with the full bounded choice page.

These are distinct observations, not a claim of full SDD acceptance. Both actual CPU image campaigns and a separately installed immutable Edge candidate remain required before merge.

The independent Playwright inventories enumerate the executed 125 source entry and 46 catalog cases, and 70 image entry cases per architecture. The image count is an inventory at this stage and does not assert that either image campaign executed or passed.

## Immutable Edge.58 build

- Runtime source: `514258c9adbd54d938e28fd65a901764a89799cc`.
- Source archive SHA-256: `91835d1b4632ddce683b217ec0b282552e3b2c13dc232d96b65c3599ecd00200`.
- Wheel SHA-256: `f3fd2b92b73e84211a2fbf2552ea6176bacfaaa12eadf2b488223d207597d3a3`.
- Local Linux ARM64 image: `sha256:4f45b662fbf0d61df5851160cb19701c975b032734f14eb44773a9218a61a4eb`.

All 231 tracked Python modules match the downloaded archive, built wheel and installed builder/final image. All four independently inventoried local UI assets match the Linux build, wheel and installed image. The normal local and Linux wheel bytes also match. The final image's architecture, Edge.58 version and source labels are verified. This is build and identity evidence; both CPU functional/browser campaigns and a separate Home Assistant installation remain required.

The initial source CI caught a stale contract assertion that still named and expected 66 image journeys. The assertion now requires the independently inventoried 70, preserving all checks for skipped, flaky and unexpected cases. All 186 Python tooling tests pass with 100% statement/branch coverage (214 statements and 98 branches), and the eight updated installer-package tests pass. This changes the CI contract and packaging metadata; the pinned runtime Python and UI bytes remain unchanged. Final-head CI is still required before merge.

## Compatibility and operational limits

The browser-journal regression executes the actual preceding Edge.57 storage adapter and controller, bundled from accepted source `272b5e8436588b5fab090622d19298371a6dc33c`. The checked-in fixture records its eight original module digests and bundle digest. Ordinary material creation, scheduled material creation and material settlement each retain seven readable legacy originals and one new original in real browser session storage. The preceding closed decoder refuses the new shape without changing the stored bytes; its controller blocks new writes while the journal is unreadable. Re-upgrade recovers all eight exact originals with their scope, stage and expiry. Capacity does not discard an unconfirmed original, and only an explicitly resolved record can be dismissed.

This qualifies the actual storage adapter and controller across rollback/re-upgrade, not a separately deployed preceding application or its complete UI. The preceding client cannot send or recover the new commands. Compatibility must not be inferred from the unchanged SQLite schema, translated into a legacy command, or achieved by clearing stored originals.

Local entry browser fixtures share ports 56174 and 56175 with Mac image campaigns. They must not overlap active image jobs. The SDD-only campaign's missing-link failure refers to the new files planned by this increment; the implementation must supply those files and pass the normal link gate.

## Case evidence map

This table maps the selected case identities to executable checks. A source check does not substitute for the pending deployed acceptance in C09.

| Selected cases | Concrete evidence and remaining qualification |
| --- | --- |
| C01, C02 | `frontend/tests/task-material-planning.test.ts` exercises title-only/no-read creation, later pages, exact zero and decimal input, duplicate rejection and the 32-line bound. `frontend/tests/tasks.test.ts` and the existing protected material HTTP cases check the canonical command and server validation. |
| C03, C10 | `frontend/tests/task-material-components.test.ts` checks separate posted, unused and pending results with server-owned unit/source labels. `tests/backend/test_task_material_http.py` exercises actual completion, replay and immutable original snapshots in both HTTP compositions. All four complete source material journeys pass with the published select correction. |
| C04 | `tests/backend/test_schedule_creation_http.py` covers both creation mappings, exact current-authorized originals, and initial/successor snapshots without repeated material effects. `frontend/tests/e2e/tasks.spec.ts` creates fixed piece and relative decimal plans through the interface in the passing complete source campaign. Both image campaigns remain required. |
| C05 | Planner retirement and denied-choice tests, the catalog-read revocation HTTP test, scheduled-original current-grant tests and the settlement authorization tests distinguish catalog discovery, linking, task-scoped actual use and current original disclosure. |
| C06, C07 | Scheduled late-write rollback/retry, corrupt durable-proof rejection, real adapter restart and actual saved-state activation in `tests/backend/test_schedule_creation_http.py`; retained historical settlement recovery in `tests/backend/test_task_material_settlement.py`; exact frozen requests and the actual preceding journal/controller rollback cases in `frontend/tests/task-journal.test.ts`. |
| C08 | EN/ES component tests and all four passing native/standalone source journeys cover keyboard, Spanish touch, retained drafts, failed choice reads and both themes using published ha-ui next.4. `frontend/tests/e2e/catalog.spec.ts` also checks the fictional creation-plan and material-outcome story without API calls. |
| C09 | Pending: both image architecture campaigns and a separately installed immutable Edge candidate, followed by scoped removal of its synthetic installation/data. No installed result is claimed by unit tests or a local wheel build. |
| C11 | `tests/backend/test_task_material_settlement.py` covers intent revision conflicts, changed-key payloads, current denial, late rollback and original lost-reply recovery. Frontend controller/HTTP tests retain and recover the exact request; the source journey checks that refill alone does not settle and that a deliberate lost-reply settlement sends one POST. |
| C12 | EN/ES actual-recording component tests retain zero/reason and require current intent review. Controller/HTTP and actual backend settlement tests validate permission, precision and zero without a movement. The source journey uses the existing separate-recording policy without adding a policy editor. |

All rows refer to `task-material-planning-Cxx` in the owning specification. Earlier case identities and owner documents remain intact. Material planning, work, verification, point awards and Inventory effects retain their separate authorities.
