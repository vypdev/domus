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
`7770b1e560800fa4bb78d36b0583b2c1beb784d7`. The previous queue-retirement runtime is published as
`fae1e6ae06993202260d765dbf27bea2144adc89` on the admitted managed ref. Edge.83
pins that exact source and archive SHA-256
`7fe626eebba24600268bca3cb032639d096fcdd8670dccc59dd03e91ea9c0a12`.
All 1,025 public archive files match their Git blobs. The wheel SHA-256 is
`641b66199213ce0e366f516911fb318ff35da7fb4f5e4632fde1434a19c5faf5`.
The earlier actual local ARM64 Edge.78 image passed six byte, listener, authority,
restart, genuine schema-20/schema-36 migration and snapshot-restoration checks.
Its installed native Home Assistant walkthrough then exposed two mobile viewport
defects: repeated Shopping entry left its heading above the screen, and focusing
an Overview item before nested control layout left the row below the screen.
Edge.78 is not accepted. Its original source, wheel, image and findings remain
distinct in `previousCandidate78`. The previous Edge.79 and Edge.80 images pass
the same six checks, including all 254 product file hashes. Their installed normal
journeys, saved literal records and public restart are qualified separately.
Review then found Edge.80's partial-household-read defect. The previous Edge.81
actual ARM64 image passes the same six checks. Its native in-place update, normal
keyboard/touch journeys, saved literal records and public stop/start are qualified
separately below. Partial-read fault injection remains an owned-fixture check,
not a claim about faults introduced into native Home Assistant.
The pre-existing specification prefix and all published #162 requirement/case
identities are preserved. Two non-normative source-assessment paragraphs now
explicitly identify the immutable base instead of describing it as current source. Backend, API, schema 37, canonical journal packet format and exact published
`@vypdev/ha-ui@0.1.0-next.5` are unchanged.

The complete current frontend campaign passes 2,212 tests across 50 files, with
all four metrics at 100% globally and per authored runtime file (121 files):
9,540 statements, 8,766 branches, 2,030 functions and 6,943 lines. Its independent
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

## Installed Edge.79 (previous viewport candidate)

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

## Durable owner after reload

The next same-head review found that mount-local member tracking could not retire
a previous member's request after reload under the same HA subject. A real
composition regression reproduced three failures: replacement-member adoption,
legacy ownerless-scope adoption and recovery after failed retirement. The same
owner already preserved its request. All four variants now pass. The persisted
scope includes the verified household/member with installation, channel and HA
subject. Destination and permission revisions do not change the owner.

The existing slot, packet fields, canonical format and original request key stay
compatible. A matching owner reopens the exact original bytes. Older ownerless or
unmatched scopes follow the journal's existing incompatible-scope retirement;
there is no lookup, resend, reassignment or change to committed server receipts.
Failure to retire blocks recovery and writes. The actual C05 browser journey also
reloads with a pending request, proves exact packet equality and zero automatic
lookups/resends, then closes the protected view. Both deployment variants pass,
as do all twelve current cases, once each without retries. The full 2,188-case
frontend run preserves all four coverage metrics at 100% with the same runtime
inventory. Catalog readiness now points to the owning executed record rather
than duplicating a test count that can drift. Edge.80 qualifies this corrected
runtime separately from the historical Edge.79 acceptance above.

## Independently verified household identity during partial reads

Review 4657842084 found that requiring display household facts unnecessarily
emptied Inventory/Shopping after a non-authentication household-read failure.
The existing HouseholdController deliberately supports this verified partial
view. Two workspace regressions reproduced the failure; the negative case keeps
both workspaces unbound when no household identity can be verified. The binding
now uses current matched administration capabilities when entry facts are
unavailable, and the same resolved household for authority revisions. All three
cases pass within the 2,190-test, 100%-on-four-metrics campaign. The actual C04
browser journey returns household-facts 503s and reloads both deployments, verifies
Shopping remains usable and navigation issues no writes, then retains every
existing stale-read, denial and independent-grant assertion. All twelve variants
pass once each without retries. Edge.81 qualifies that runtime; the historical
Edge.80 normal native journeys, saved records and real stop/start are retained
separately and do not establish acceptance of this partial-read correction.

## Installed Edge.81 (previous partial-read candidate)

Supervisor reported installed Edge.80, then installed Edge.81 after the in-place
update of the same independent app. The DOM-backed module basename is
`index-BzSz5xDX.js`, matching the qualified wheel. No backup or new persisted
records were created for this update. The English light-mode 1120-by-844 keyboard
journey and Spanish dark-mode 390-by-844 actual touch journey preserve Stock and
Shopping drafts in both directions. Shopping's focused heading is visible below
fixed navigation (68.16–106.55 desktop; 67.77–106.16 mobile). Overview's focused
Tea row remains within the 804-pixel mobile frame at 389–414.59, below navigation
ending at 56. Temporary viewport, touch and media overrides were reset.

An actual public Supervisor Stop reached **Detenido/Iniciar**, and Start reached
**En ejecución/Open Web UI** at version Edge.81. Fresh app entry retained Tea
quantity two/Urgent and Bags quantity one/Low, both original LF/HT/emoji notes
and literal markup-looking text with zero HTML children. Recorded, reserved and
available stock remain zero; movement history, purchases and purchase sessions
are empty. The app is stopped again. The exact same synthetic app/data/source
permanent-uninstall confirmation requested earlier remains pending; no deletion
has been inferred from elapsed time or general cleanup authorization.

These installed observations exercise the normal C01–C03 journeys and data
compatibility. The corrected partial-household-read failure and cross-member
pending-packet retirement are exercised by the current source/browser fixtures;
no private Home Assistant APIs, hidden state, injected native failures or clock
changes were used. At packaging head `5f0bb08`, Review, Verification, Commit and
Branch Sync pass and all five historical findings are resolved. The final
evidence head still requires its own applicable CI and review, followed by normal
merge, destination CI/Branch Sync and native issue closure.

## Active destination refresh and denied-command guidance

The final evidence-head review found that Stock refresh could resume the former
Shopping item read. A Shopping-only denial then retired the independently readable
Stock view. Real composition regressions reproduce this for manual refresh and
post-save refresh. The shared controller now retains Shopping projections while
Stock refreshes, and revalidates them only on Shopping entry with the current
route. It preserves drafts, selections, pending command ownership and current
scope checks. Failed catalog proof or scope retirement stops that continuation.

Two EN/ES regressions also reproduce purchase denials recommending Inventory
access. Feedback now distinguishes Shopping request access, Shopping management,
Inventory receipt posting and the combined grants for posted corrections/returns.
The existing C02 actual-browser journey verifies zero hidden Shopping reads during
Stock refresh even when those reads would return 403. C04 verifies the denied
purchase message, retained purchase fields and an explicit successful retry. All
original assertions remain. All twelve variants pass once, without retries, and
all 2,196 frontend tests preserve global/per-file 100% on all four metrics. The
independent source coverage audit, types, SDK catalog and package/docs checks pass.

Edge.81's installed acceptance above is historical and does not include these
last two runtime corrections. The immutable Edge.82 actual local ARM64 image passes all six byte, authority,
standalone, restart, genuine schema-20/schema-36 migration and snapshot-restore
checks in 18.28 seconds. Current full CPU images, installed Edge.82 walkthrough
and final same-head checks remain required.
The two stale source-assessment paragraphs in the Action-published unit now name
the immutable base explicitly. The preceding owner prefix and every published
requirement/case row remain byte-identical; no acceptance identity was changed.

This is the Edge.82 packaging snapshot. The linked [PR #163](https://github.com/vypdev/domus/pull/163) retains final current-head CI, review and installed acceptance. Earlier installed candidates above remain historical; their observations do not establish acceptance of a later source.

## Retiring a queued destination when leaving Shopping

Review 4658107744 reproduced a remaining route race: resetting the route tracker
to null before comparing an Inventory route left a queued Shopping object/timer
alive. A later catalog completion could consume it outside Shopping. Both a
controlled busy-catalog composition case and an already-queued-tick case fail
before the fix. The actual C02 browser variants also fail against all four exact
compiled Edge.82 resources: holding the catalog, visiting Shopping then Inventory,
and releasing the read causes a hidden Shopping 403 to disable Stock registration.
The original reports, screenshots and traces are retained.

Each hash change now retires the old Shopping object/timer before resetting its
route tracker. No command or original recovery owner is cancelled. Both
composition regressions pass and prove that a later legitimate Shopping entry
still works. All twelve actual variants pass once in 30.2 seconds without retries,
with unchanged assertions and deadlines. All 2,198 frontend tests pass; the four
coverage metrics remain 100% globally and per file (9,524 statements, 8,748
branches, 2,027 functions, 6,931 lines). Types and the independent source-inventory
coverage audit pass. The six native case identities remain unchanged.

Edge.82's normal installed EN/ES keyboard/touch, Stock-refresh/reentry drafts,
literal saved records and public stop/start are independently observed. Its
matching module is `index-CpDS3NEI.js`; the selected mobile Tea row after restart
is uniquely identified, focused and visible at 389–414.59 in the 804-pixel frame.
Both saved notes/priorities/quantities remain exact; stock and movement history
stay zero, with no purchases or sessions. It is stopped, with the same exact
app/data/source cleanup confirmation pending and no new household records or
backup. This normal native qualification does not accept the known queued-read
race: the next immutable Edge.83 and final current-head acceptance remain required.

This Edge.83 packaging snapshot pins the queue-retirement runtime. The linked PR retains final current-head CI/review and installed acceptance; the previous Edge.82 normal walkthrough does not establish this correction's acceptance.

The current Edge.83 actual local ARM64 image passes all six exact-byte, authority, native/standalone listener, restart, genuine schema-20/schema-36 migration and snapshot-restore checks in 18.44 seconds. Its native installed walkthrough and complete current-head CPU/source CI remain required.

## Retiring an entry that has already begun refreshing

Review [4658614224](https://github.com/vypdev/domus/pull/163#discussion_r4658614224)
identified a continuation beyond the former queued tick. After Stock refresh, a
Shopping entry could begin its own catalog refresh, leave for Stock, and then
start a hidden Shopping read. A Shopping-only 403 could disable Stock. Four
controller cases and both actual compiled Edge.83 C02 variants fail before the
correction; the original reports, traces and screenshots are retained.

A destination identity now retires when activity changes, on every hash change
and at widget teardown. Entry refresh, retained projection chains and paged item
reads check that identity before starting another Shopping read. Leaving and
returning cannot adopt the retired continuation. An admitted read and the original
command are allowed to finish; no command, pending packet or recovery owner is
cancelled or resent. Fourteen controller regressions cover entry, hidden admission,
all six retained projection stages and paged-item continuation. The whole 2,212-test
frontend campaign passes with all four coverage metrics at 100% globally and per
file, and the independent authored-file audit passes. Types and product build pass.
All twelve actual browser variants pass once in 29.1 seconds with zero retries
and unchanged prior assertions and deadlines. The six native case IDs are unchanged.

The installed Edge.83 normal walkthrough and earlier CI results remain historical.
They do not accept this newly reproduced race. Immutable Edge.84 packaging, actual
image qualification, native installed acceptance and full same-head checks are
required before merge. Final terminal observations belong to the linked PR.
