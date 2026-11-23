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
focused browser variants also pass on the actual image. Installed acceptance and
the complete final-head amd64/ARM64 CI matrix remain pending in the receipt.
The image-browser guard increases from 90 to 98 executed variants because this
increment adds eight browser variants to the existing four recurrence variants;
it does not add or claim eight owning specification cases. Both architectures
retain their zero-skip, zero-flaky and zero-unexpected guard.

This bounded correction does not establish full M2 acceptance, owner acceptance,
cross-domain ledger effects, HA entity qualification or distribution readiness.
Historical Edge.86 and Unicode receipts retain their original identities and
claims. Edge.86 remains the compatible rollback until Edge.87 is qualified.
