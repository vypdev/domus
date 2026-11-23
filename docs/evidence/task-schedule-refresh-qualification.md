# Tasks after a saved schedule change

Domus #171 corrects the Tasks projection after a confirmed recurrence apply or
recovery of that original apply. The immutable Edge.87 runtime is
`17c1ef424ac9f3fae67dd076bee121947d9065c7`; its exact source archive, wheel and
packaged UI identities are recorded in [the receipt](task-schedule-refresh.json)
and [the app pin](../../addon-edge/artifact.json). All 250 Python product files,
schema 37 and the published ha-ui `0.1.0-next.5` cohort are preserved.

The installed Edge.86 journey reported success while the selected cancelled
original still appeared Available with Claim and completion controls. The new
source regression reproduced that stale list before the correction. A confirmed
current effect now reads authorized list/detail facts through the existing Task
and Household controllers. It preserves the saved schedule receipt, original
requests and unrelated drafts. A failed read removes stale task commands, explains
that the schedule change was saved, and focuses **Refresh tasks**. That explicit
retry restores the selection without another apply POST. Preview, rejected or
uncertain writes and historical receipts do not trigger this reconciliation.
Navigation and current participant changes retire the old continuation; fresh
authorization never restores an old task target.

The source tests cover recurrence-calendar-R5 and the existing
recurrence-calendar-C31 UI journey. Original-apply recovery supplements C33, with
its reservation and demand assertions still owned by Inventory. No owning IDs or
specification inventories change. Twelve protected browser variants exercise save,
lost-response GET recovery and read failure in native and standalone compositions:
English desktop keyboard and Spanish 390 px touch. The 2,240 frontend tests cover
all 121 runtime files at 100% statements, branches, functions and lines, globally
and per nonempty file. All 153 composed source-entry variants and 68 compiled
catalog variants pass with zero skipped, flaky or unexpected cases.

The local ARM64 pinned image passes the product-file comparison, native launcher
authorization/storage/restart and exact standalone bundle checks. Its twelve
focused browser variants also pass on the actual image. This source receipt keeps
those identities fixed. Installed acceptance and the complete exact PR-head
amd64/ARM64 matrix are reported separately in [PR #172](https://github.com/vypdev/domus/pull/172)
and are required before merge; private Home Assistant snapshots remain local.
The image-browser guard increases from 90 to 98 executed variants because this
increment adds eight browser variants to the existing four recurrence variants;
it does not add or claim eight owning specification cases. Both architectures
retain their zero-skip, zero-flaky and zero-unexpected guard.

This bounded correction does not establish full M2 acceptance, owner acceptance,
cross-domain ledger effects, HA entity qualification or distribution readiness.
Historical Edge.86 and Unicode receipts retain their original identities and
claims. The accepted Edge.86 rollback is retained while the later candidate is qualified.

## Saved result visibility

Installed Edge.87 confirmed both apply/recovery journeys and retained its six
synthetic rows across public restart. On a 390px screen, however, a late task
allocation-settings read expanded the card above the focused result. Its heading
moved to y849 in the 804px Ingress viewport. Functional effects were correct, but
that result was not accepted as finished UX. The private original snapshots and
the [frozen source record](task-schedule-refresh.json) keep their original claims.

Edge.88 pins runtime `82eacbd10218154ca1eb38f1f03d51d768dd3aff` for the
[visibility follow-up](task-schedule-refresh-focus.json). While a saved result
owns focus, parent layout changes keep it visible. A newer focus, keyboard,
pointer or wheel input retires that continuation. A new result or removal also
cleans up its observer and input listeners. Embedded reviews use their content's
height rather than reserving an otherwise empty viewport.

The browser regression holds the real allocation-settings response until after
the save acknowledgement, then requires the complete saved heading to remain in
the viewport after the task card expands. It reproduced a viewport ratio of 0
before the correction. Current source/image results are recorded in the
follow-up receipt; installed and exact PR-head acceptance remain separate in
[PR #172](https://github.com/vypdev/domus/pull/172).

The corrected source passes 2,242 frontend tests with all four coverage metrics
at 100% globally and per nonempty runtime file, all 153 composed entry variants
and 68 catalog variants. The pinned local ARM64 image passes four
package/listener checks and all twelve focused browser variants, including the
late-settings response. All browser inventories report zero skipped, flaky or
unexpected cases.

The earlier amd64 job passed 61 container cases but failed its generic UI delivery
check because it still expected the historical Edge.86 Unicode bundle. That
check now uses the current reviewed app manifest; byte, protected-delivery and
historical-identity assertions remain intact. Both architecture jobs still must
pass the complete inventory on the final head.
