# Shopping workspace navigation qualification

[Issue #162](https://github.com/vypdev/domus/issues/162) implements the bounded
[owning unit](../../specs/application-experience.md#proposed-change-open-shopping-as-a-direct-household-workspace).
The [implementation map](../../specs/shopping-workspace-navigation.md) links its
eleven requirements and six scoped acceptance cases without recounting them.
The [machine-readable record](shopping-workspace-navigation.json) separates
executed source checks, compiled images, installed Edge and final CI.

## Current source observations

The native Action published specification commit
`a67ee381043a8e34ca9fec02b811c9cd9d330078` from accepted base
`7770b1e560800fa4bb78d36b0583b2c1beb784d7`. The implemented runtime is published as
`8ff8bf2d037b6726c00d9bce5a79f7f4086b3077` on the admitted managed ref. Edge.79
pins that exact source and archive SHA-256
`52075d71444437cdf36a307d65785a8d1e914af69d45d2c381b5dd97d56e53aa`.
All 1,025 public archive files match their Git blobs. The wheel SHA-256 is
`8eb1af9c77efae0adfe475003d1220165dde21cc74edd4faef10088058b4585e`.
The earlier actual local ARM64 Edge.78 image passed six byte, listener, authority,
restart, genuine schema-20/schema-36 migration and snapshot-restoration checks.
Its installed native Home Assistant walkthrough then exposed two mobile viewport
defects: repeated Shopping entry left its heading above the screen, and focusing
an Overview item before nested control layout left the row below the screen.
Edge.78 is not accepted. Its original source, wheel, image and findings remain
distinct in `previousCandidate78`; the new Edge.79 image passes the same six checks, including all 254 product
file hashes. Its installed upgrade also passes the native acceptance below.
The pre-existing specification prefix and published #162 unit are
preserved. Backend, API, schema 37, journal serialization and exact published
`@vypdev/ha-ui@0.1.0-next.5` are unchanged.

The complete current frontend campaign passes 2,184 tests across 50 files, with
all four metrics at 100% globally and per authored runtime file (121 files):
9,504 statements, 8,719 branches, 2,025 functions and 6,914 lines. Its independent
source-inventory coverage audit passes. Runtime/catalog TypeScript checks,
product Vite build and the actual wheel package test pass. All 250 Python module
bytes equal accepted Edge.77; the four compiled UI resources match the new wheel.

The six new native cases pass twelve Ingress/standalone variants, once each with
zero skipped, flaky or unexpected results and zero retries. They cover keyboard
and touch, both themes/locales, item/history entry, literal drafts and original
receipt recovery, separate reader/requester/shopper authority, denied/stale
reads, logout and actual restart/restore. The prior four annotation journeys and
both complete shared-workspace journeys also pass with their original domain
assertions and explicit visits to the correct Shopping or Stock owner. The
complete source browser campaign executes all 141 variants: 139 pass and two
barcode-403 cases retain an obsolete generic-unavailable message expectation.
The actual explicit denial was verified; both expectations now require that
denied guidance; both targeted regressions pass, including the retained
private-fact removal, recovery focus, barcode and stock assertions. Final same-head
CI must execute the entire inventory without failures.

All 68 built-catalog tests pass, including the eight retained Shopping states.
The 42 Node policy cases pass with all four tooling coverage metrics at 100%;
99 Python architecture/CI-contract cases and the documentation-link check pass.
The unmodified SDK catalog entrypoint `main(['--write'], process.cwd())` followed
by `main([], process.cwd())` validates all eleven capabilities and the generated
view. The new implementation note belongs to application-experience; it does
not introduce a duplicate native inventory or claim the wider capability done.

A new browser regression reproduced rapid Back navigation leaving focus in the
previous tab when two delayed hash events observe the same final item URL.
The composition now requests destination focus and schedules the current item
read even in that ordering. Both deployment variants pass the red/green
regression. Existing source coverage and semantic assertions remain enforced.
The stronger C01/C02 regressions also reproduce the installed Edge.78 geometry
failures against its old bundle. With Edge.79's runtime, all twelve variants pass:
the Shopping heading is visible below fixed navigation, and each focused item
is inside the mobile viewport after direct entry, reload, history and Overview.
Only local fixture ports differ while concurrent self-hosted CI owns the canonical
ports; reverse substitution verifies all other authored test bytes are identical.
There are no retries or reused fixture servers. A later user focus wins over a
pending post-layout scroll. Review regressions also verify that stale source
buttons stay disabled until refresh and that base Shopping retires an item filter
and reads the shared first page without a command.
The CI selection explicitly includes the new file and requires all 86 actual
image browser journeys with zero skipped, flaky or unexpected results and zero
retries in each CPU job. Actual execution of those jobs remains pending.

## Remaining qualification

Complete the full source browser campaign and retain its original result. Qualify both current actual CPU images, including original
receipt/ledger compatibility and restart/restore. Record source, wheel, image,
runtime and package identities, review responsive focus/contrast and permission
states, then retire only owned obsolete QA artifacts. Same-head CI, Branch Sync,
review/progress, normal merge, destination checks and native issue closure remain
required. This is one bounded navigation increment, not completion of the wider
application-experience capability or M4/M5 roadmap.

## Installed Edge.79

Supervisor reported installed Edge.78 and available Edge.79 before an in-place
update of the independent synthetic installation. It then reported installed
Edge.79. The native UI preserved its household, Tea product and two manual extras:
Tea quantity two/Urgent and Bags quantity one/Low. Both notes retained their exact
LF, HT, emoji and literal markup-looking text, with no HTML children. A public
Supervisor restart and fresh app entry preserved those values. Recorded, reserved
and available stock remain zero; movement history, purchases and sessions are empty.

The Spanish dark-mode 390-by-844 touch walkthrough used actual touch input for
tab overflow, Shopping and Inventory. The focused Overview product is at
389–414.59 within the 804-pixel Ingress frame, below navigation ending at 56.
Repeated Shopping entry reveals its heading at 67.77–106.16 and focuses its active
region. The English light-mode 1120-by-844 keyboard journey reveals the heading
at 68.16–106.55. Stock and Shopping drafts and the literal unsent note survive
switching between those destinations. Temporary viewport, touch and media
overrides were reset. These observations directly exercise C01–C03; the source
and both-CPU campaigns retain the broader permission, interruption and restore
inventory.

The owned app is stopped. Home Assistant's permanent-uninstall warning requires
action-time browser-policy confirmation for the synthetic app/data and exact
temporary source; that confirmation is pending. No backup was created. The
original twelve apps and eight repository sources remain protected. This native
acceptance does not substitute for current same-head CI or final review.
