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
file hashes. Its installed upgrade remains pending. The pre-existing specification prefix and published #162 unit are
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

Complete the full source browser campaign and retain its original result. Qualify an immutable Edge candidate
in real Home Assistant and both current actual CPU images, including original
receipt/ledger compatibility and restart/restore. Record source, wheel, image,
runtime and package identities, review responsive focus/contrast and permission
states, then retire only owned obsolete QA artifacts. Same-head CI, Branch Sync,
review/progress, normal merge, destination checks and native issue closure remain
required. This is one bounded navigation increment, not completion of the wider
application-experience capability or M4/M5 roadmap.
