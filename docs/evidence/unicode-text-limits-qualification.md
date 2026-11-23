# Unicode text limits qualification

[Issue #165](https://github.com/vypdev/domus/issues/165) repairs existing text
contracts in product registration, Shopping names, storage locations and reasons,
reward titles/cancellations and schedule review. The [machine-readable record](unicode-text-limits.json)
separates baseline reproduction, local execution, historical failures, immutable
image qualification and installed acceptance. Final repository merge gates and
their exact commit are tracked on [PR #166](https://github.com/vypdev/domus/pull/166).

## Existing contract and observed failure

The accepted develop baseline `487e157ff4b95b4ba6debf1543d816f95c985481` has the
same tree as `8a63abb9032198f90aa20e1168f01ebd2912112f`. Native typing of 160
supplementary characters retained only 80 in four actual compiled views: Product
name, Extra item name, Untracked item name and Reward name. ASCII 160 passed.
The UI actually stored the 80-character product name, while the same protected
API accepted and returned the exact 160-character value. The observed compiled
JS/CSS match accepted Edge.85. The original observations, receipt, recipe and
independent asset qualification are retained; this was not installed HA proof.

Native HTML maxlength and the published single-line Field count UTF-16 units.
The existing domain counts Unicode codepoints. Corrected single-line fields use
the public Field's larger safety bound and keep application validation at the
existing 160/80/240/1,000-codepoint limit. An extreme value truncated at the
16,384-unit safety bound still exceeds every business maximum and cannot become
a valid silently shortened submission. The public Textarea already counts
codepoints and supplies schedule-review's 1,000-character limit. No domain text
policy, schema, command/receipt identity or permission is changed.

## Bounded integration

All affected controls use exact published `@vypdev/ha-ui@0.1.0-next.5`. Named
FormData, current draft revisions/fingerprints, default/reset ownership and blocked
edits remain covered. A completed own extra resets while refreshing; a later or
unrelated draft survives. Registration resets revealed validation while retaining
the selected base unit for the next product. Over-limit drafts remain editable
and produce no command. English and Spanish messages retain the existing limits.

A complete permitted reward response can contain 64 offers and 25 request snapshots,
each with 160-character titles and a 1,000-character cancellation reason. A
supplementary-character page exceeded the previous 64 KiB read bound and failed
before parsing. Reward-page GET now has a distinct 256 KiB budget. Streamed and
declared-length overflow still fail; ordinary reads and command/recovery replies
retain 64 KiB. Endpoint shapes, record limits, charset, no-store, same-origin and
current authorization checks remain unchanged.

Long reward options must fit a narrow grid. Its primary button uses the current
surface as its on-accent color in both themes. The final four composed variants measure actual painted contrast at 7.11:1 in
light mode and 9.14:1 in dark mode. Focused inputs sit at least 80px from the
viewport top, below the 56px sticky navigation. The named public input part
provides scroll margin without changing command or navigation ownership.

The original owning requirements remain in [Inventory](../../specs/household-inventory.md),
[Shopping](../../specs/shopping-management.md), [Rewards](../../specs/points-rewards.md)
and [Recurrence](../../specs/recurrence-lifecycle-calendar.md). Their exact relevant
identities are listed in the JSON record. No native requirement/case ledger is
replaced or renumbered, and this bug does not complete those broader capabilities.

## Immutable Edge.86 candidate

The public runtime is `8b2660d282f7e58dedfccd6b11ba53eabe54b2e6`. Its archive SHA-256 is
`a80f2f1201f2028c053a15f71f3b8b2d2c7896e38ea86cc17fa13c0c83d6e0ce`; every one of its 1027 tracked Git blobs matches.
Wheel SHA-256 is `45672f4c0b1ec1e683e9a4bd34369bff8d5223ec97b609122d10e4e150779867`. All 250 Python modules remain
byte-identical to accepted Edge.85. The actual ARM64 image `sha256:829e29de1e7a5e5b9b4dce6a8d34457408e44b07942c512a805c629030733bb9`
installs all 250 Python modules and all 4 UI files byte-for-byte from that wheel.
Six real-image checks pass in 22.74 seconds, including both listeners, authority,
restart and genuine schema 20/36 upgrade/snapshot restoration. These functional image checks are separate from the actual installed acceptance below
and the final exact-head repository gates on the pull request.

An initial verifier inventoried a nonexistent `frontend/dist` and recorded an
empty asset map; its original closed record is retained. Vite actually writes
`backend/src/domus/ui`. The corrected filesystem comparison matches the wheel.
Four fresh actual-browser journeys now also capture every received JS/CSS body:
all observed response hashes match the frozen wheel, rather than merely matching
a build directory. The actual module is `assets/index-DTeCBXBi.js`, SHA-256
`3a60cd520666c663fffabff0c68fa7dff66d1d051e66d31bcc3dc113a0c04e40`.

## Executed source checks and remaining gates

The complete frontend passes 2,229 tests across 50 files. All four metrics are 100%
globally and per file: 9,599 statements, 8,807 branches, 2,035 functions and 6,978
lines. The independent authored-file audit accounts for 121 runtime files
(114 nonempty and 7 empty). Runtime/catalog TypeScript, product build, Node
TypeScript, 42 Node-policy tests/all four 100%, the native catalog validator and
68 catalog-browser variants pass. All 48 CI-contract tests pass after updating
the strict actual-image inventory from 86 to 90 for the four new Unicode variants.
Runner placement, exact released action tags, deadlines and zero retries remain
unchanged.

The first complete composed suite ran 145 variants: 139 passed and 6 failed. Four
calendar failures locate the retired native textarea instead of the public named
Textbox; two workspace failures require the former outer alert instead of the
shared Field's described, live inline error. Their original diagnostics are
retained. Current semantic selectors keep every actual write, original-key,
permission, retained-state, restart and restore assertion. All six adapted calendar/workspace variants subsequently pass with their
original persisted-effect and recovery assertions. The final four Unicode
variants pass again with real painted contrast, focus and width checks, once
each with zero retries. The combined final ten-variant execution passes once in 124.60 seconds, with no skipped, retried or flaky cases. These local checks are not same-head CI or
installed acceptance.

The packaging-head CI `75724c862c2b0a4028a0b8714d0ed5bcaa9f3046` subsequently
passes all 145 source and 68 catalog variants, each exactly once with zero skipped,
retried or flaky cases. Its downloaded original JSON reports are independently
counted. Its original coverage report confirms all four metrics at 100% globally
and for all 121 frontend runtime files. The complete backend job passes all
6,040 cases with full coverage; amd64 passes all 62 container and 90 browser cases.
Final exact-head CI, substantive review, verification, both image architectures
and native-HA module coverage remain repository merge gates tracked on PR #166.
No Stable release or deployment is authorized by this increment.

## Installed Home Assistant acceptance

Home Assistant builds and installs Edge.86 from the published temporary source.
Its actual received JS and CSS bodies match the frozen wheel hashes. The original
public Supervisor log confirms successful installation even though a concurrent
Home Assistant Core restart interrupted the frontend response. The new app uses
only the documented local public origin. No other installation is modified.

English desktop/light/keyboard and Spanish 390px/dark/actual CDP touch exercise
the public UI. A 161-character product draft remains intact, receives its
localized error and sends no command; the complete 160-character product then
saves. Registration clears its error and retains the chosen base unit. An
80-character location, 240-character stock reason, 160-character manual extra,
160-character untracked purchase and 160-character reward save without truncation.
The Spanish reward draft also retains all 161 characters after an actual touch,
shows its translated error and sends no reward command. Native measured contrast
is 7.11:1 in light and 9.14:1 in dark. The focused field remains below navigation,
and the mobile document is exactly 390px wide.

A public Stop followed by Start retains both complete product names, location,
exact stock and reason, extra, purchase and one reward. Fresh protected UI reads
verify those values after reopening; no duplicate reward appears. The app is
stopped again, automatic behavior remains off, temporary browser overrides are
reset and the owned test tab is closed. Representative original screenshots and
the frozen installed receipt remain with the immutable candidate. This installed
proof covers native Ingress; the separate real-image/source campaigns qualify
both listeners, broader permission/concurrency/recovery and restoration behavior.

## Initial source CI diagnostics

The first source CI confirms 2,229 frontend unit tests and a successful complete
backend job. Wheel acceptance and amd64 UI delivery still compared the changed
bundle with the historical Edge.85 record. The amd64 container campaign passed
its other 61 cases. Current package tests now use this increment's frozen UI
manifest; historical Edge.85 evidence and all byte comparisons remain intact.
All 17 local package/documentation contracts pass. The subsequent packaging-head source, wheel and amd64 gates pass. Final checks
for the pull request head, including any qualification-only commit, remain required.
