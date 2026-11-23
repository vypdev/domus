# Tasks after a saved schedule change

The current Edge.89 pin uses runtime `5cb600dff66d5a54de23ffdef8b386fc118a4fbc`.
Its [scope-recovery qualification](task-schedule-refresh-scope.json) and
[current app manifest](../../addon-edge/artifact.json) retain exact source,
wheel and UI identities. The earlier Edge.87 and Edge.88 records below remain
historical qualifications, with their original source identities and limits.
Schema 37, all 250 Python product files and exact ha-ui `0.1.0-next.5` remain unchanged.

## Initial projection correction (Edge.87)

Domus #171 corrects the Tasks projection after a confirmed recurrence apply or
recovery of that original apply. The immutable Edge.87 runtime is
`17c1ef424ac9f3fae67dd076bee121947d9065c7`; its exact source archive, wheel and
packaged UI identities are recorded in [the receipt](task-schedule-refresh.json)
and its original immutable pin receipt. All 250 Python product files,
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

## Recovery before task scope is available (Edge.89)

The substantive review of `53dd824` found that a temporary session or task-access
read could clear the task scope before the confirmed receipt was restored. The
next explicit refresh then lost that continuation. The source regression
reproduced both failures before the correction.

While task proof is unavailable, the independently reverified household/member
can see only a generic saved-change acknowledgement and the focused read retry.
Private receipt details, task facts and schedule commands remain hidden. An
explicit **Refresh tasks** can fail repeatedly without losing the confirmation.
Fresh matching task authorization restores the original receipt and selected
occurrence without another apply POST. A changed member, denied task access,
revoked schedule-review permission or navigation retires the continuation.
Unavailable and malformed current reads focus recovery without taking over a
later draft edit.

The current source passes 2,251 frontend tests with all four coverage metrics at
100% globally and per nonempty runtime file, 157 composed entry variants, 68
catalog variants and 42 Node tests. Four new native/standalone EN keyboard and
ES390 touch variants exercise this pre-scope failure. Together the existing
save, original-GET and read-failure journeys now have sixteen focused variants;
the complete actual-image guard increases from 98 to 102, retaining zero skipped,
flaky or unexpected results. These are execution variants, not new owning cases.

The pinned local ARM64 image passes four package/listener checks and all sixteen
focused browser variants with zero skipped, flaky or unexpected results. The
local legacy-upgrade case is excluded from this bounded package campaign; the
complete architecture CI inventories remain mandatory. Installed acceptance and the complete
final-head amd64/ARM64 CI and substantive review remain separate merge gates in
[PR #172](https://github.com/vypdev/domus/pull/172). The generic current-wheel test
now reads the current app manifest, preserving its byte, wheel, licence and
fixture-exclusion checks and the original historical Unicode receipt.
