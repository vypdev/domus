# Shared entry authentication rejection

Issue: [#146](https://github.com/vypdev/domus/issues/146).
Accepted owners: [foundation invariant 4.3.3](../../specs/platform-foundation-identity-sqlite.md#43-fixed-productsafety-invariants)
and [ENTRY-02, ENTRY-05 and ENTRY-06](../../specs/household-entry-interface.md#4-goals).

## Defect and resulting behavior

Installed Edge.56 client fault injection demonstrated that a strict, same-origin Inventory 401
could retire Inventory while leaving the parent household and current-access presentation visible.
The fixture replaced one owned response after the actual GET returned 200; it did not revoke a real
HA account. Mounted Ingress and standalone regressions reproduce the retained proof before the fix.

The shared HTTP adapter now reports a validated protected 401 to the document's captured proof owner.
That owner invalidates entry proof, cancels owned views and hides their private facts. The interface
focuses the existing native reopening or standalone sign-in action once it becomes available. Setup
drafts are retired with unproven identity; original command journals remain retained. The server's
authentication, permissions, CSRF, storage schema and absolute session deadline are unchanged.

Each request captures its installation/channel/subject, live request signal and exact proof lifetime
before sending. Aborted requests, replaced proof, restored document lifetimes and disposed widgets
cannot expire a newer view. No observer is attached to the original page fetch function or shared
globally. The response must pass the existing URL, redirect, MIME, caching, stream, JSON and blocked
failure checks before reporting rejection. Unbound sign-in reads do not invalidate unrelated proof.
HTTP 403 stays a granular permission denial; malformed responses and technical unavailability do
not become an authentication rejection or acquire fresh proof.

## Existing acceptance cases

| Existing entry cases | Concrete checks |
|---|---|
| C13, C15 | Mounted Ingress/standalone protected 401 removes entry, household, administration and Inventory without a new session read; 403/503 retain their existing scope and recovery rules. |
| C16 | Runtime tests fence cancelled requests, different installation/channel/subject, replaced proof, persisted page restoration and disposed lifetime. |
| C23 | Strict HTTP tests reject foreign or malformed 401 responses before notifying any proof owner. |
| C07, C12, C17 | A protected command rejection retains its exact prepared journal; deliberate fresh verification exposes original recovery without another POST. Both real SQLite compositions commit an association once, lose its reply, expire client proof on a secondary 401, reload deliberately and recover the same operation/association by GET. |
| C33, C34, C35, C36 | Existing desktop keyboard and 390 px touch journeys retain current review/result focus, unavailable retry, granular 403 refresh, original request focus, EN/ES and light/dark checks; shared expiry moves focus to the existing verification action. |

The barcode journeys retain their stale-association race, long-name layout and stock/history checks.
Signed-out language selection remains presentation-only; a retired member's temporary language does
not survive as an identity preference. No planned specification case is removed or renumbered.

## Qualification boundaries

Source tests, actual amd64/ARM64 image runs and immutable installed Edge acceptance are separate
gates. Local/CI results and the new candidate's immutable hashes are recorded here as they complete.
The Edge.56 observation diagnoses this defect; it does not qualify the corrected runtime.
Only Edge installation is authorized. Stable/distribution acceptance remains open in the roadmap.

## Local source checkpoint — 2026-11-20

- The two mounted regressions fail before the runtime correction and pass afterward.
- Strict runtime/catalog types pass; 1,951 Chromium unit/component cases cover all 106 runtime file records at 100% for every supported metric, globally and per file.
- All 121 composed source journeys and 45 catalog journeys pass with zero skips, unexpected results or retries. The two strengthened barcode journeys recover the exact original operation after shared proof expiry.
- All 42 Node policy and 51 architecture cases, plus documentation checks, pass.
- Original reports, coverage, failure log and 14 barcode/entry screenshots are retained separately from generated build outputs. Both actual-image jobs and installed corrected Edge acceptance remain pending at this checkpoint.

## Immutable Edge.57 checkpoint

- Runtime source: `272b5e8436588b5fab090622d19298371a6dc33c`.
- Source archive SHA-256: `352f69ca646ad276454e6bcb442fa8a3fa1f81826e55bf3daeb3a7c8ba957aad`.
- Wheel SHA-256: `f5a1075d1313eebc01534b8a6aba6116e27c6b15bb2ae7a5b04d31962fcc2ea0`.
- Local final ARM64 image: `sha256:fe9dfa9521a3737408a8ac7ebb97de05c1b7c884c733764958943f4f3da286ca`.
- All 231 Python modules and four UI resources match the Git/archive, wheel, Linux builder and final local image; the normal local and Linux wheels match byte for byte. Version/source labels are checked independently.
- Storage schema remains 35. This local ARM64 inspection is separate from both CI architecture campaigns and the Supervisor-installed candidate, which remain pending.

The first required wheel gate detected that the current UI evidence map in
[task-navigation-integration.json](task-navigation-integration.json) still described Edge.56.
The map is now updated from the independently matched Edge.57 bytes, with the previous map retained.
The complete wheel/asset/license and fixture-exclusion guard passes locally. This evidence correction
changes no runtime, archive, wheel or candidate version; the original two CI job logs are retained.

## Reviewed PR and post-merge qualification

PR [#147](https://github.com/vypdev/domus/pull/147) passed all checks at
`66dd70a7965bfee7088ba7da8312cdba7d46f2bb`: 5,583 backend cases with all 231 modules at
100% supported coverage, all source/catalog journeys and all 66 journeys on each actual
amd64 and ARM64 image. The amd64 image executed under emulation on the self-hosted Apple
Silicon runner; this is not physical x64 hardware acceptance. Installed immutable Edge.57
also passed the separate original-request, shared-401, granular-403, keyboard/touch,
theme/locale and stop/start persistence checks with owned synthetic data.

The exact merged tree at `10e153a32937ef1bfd5b81adfc6dc8929d9ea220` passed Branch Sync,
backend and source checks, but its amd64 browser campaign passed 65 of 66 journeys.
The standalone barcode case failed while reading `Response.json()` from Chromium after
the application had already displayed the recovered association. The retained trace
records HTTP 200 followed by `net::ERR_ABORTED`; the browser cancellation trigger is not
independently established. The original report, trace, failure screenshot and job log
are retained. That failed CI is not treated as an accepted baseline.

Issue [#148](https://github.com/vypdev/domus/issues/148) corrects only this test observation.
The exact original GET now uses Playwright's documented
[upstream fetch and unchanged fulfillment](https://playwright.dev/docs/api/class-route#route-fetch)
to retain the real receipt bytes before delivery, with redirects and retries disabled.
It still requires one recovered receipt, the same operation and association, one association
POST, and all existing UI/focus, authentication, granular-denial and stale-association checks.
No case is removed or retried, and runtime, packaging, schema and Edge.57 bytes are unchanged.
Both protected source journeys and complete same-head CI remain required for this correction.
The two corrected local source journeys pass in 12.8 seconds with no skips, unexpected
results or retries. Both original receipt bodies and 14 screenshots are retained. Runtime
and catalog types, documentation links and the rebuilt UI byte comparison also pass.
