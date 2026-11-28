# Current eligibility for reviewed skips

Domus issue [#174](https://github.com/vypdev/domus/issues/174) supplements the existing
recurrence-calendar-C30 witness under recurrence-calendar-R3/R5. It adds no owning cases,
missed-work policy, storage schema or permission. The bounded source receipt is
[fixed-skip-discovery.json](fixed-skip-discovery.json).

The scheduling target uses the same fixed-skip plan as preview and apply. A reason-free
selection identifies the current rule, slot and occurrence revisions. A real skip request
still requires the member's reason and keeps the existing canonical request document.
Discovery records no preview, receipt, history, transition or scheduler progress.

The rule and slot must match the current occurrence. The task must be available or assigned,
with unstarted work history, an opted-in missed-work policy and a consistent effective
deadline. A timed deadline must be strictly before the trusted current instant. A date-only
deadline must be before the current local date in the rule's approved policy. Rescheduling
changes the effective deadline used by discovery. Reopening completed work does not erase its
history protection. The existing paused-rule behavior remains owned by the shared planner.

Current management authority is checked before discovering private work or consulting time.
Expected applicability conflicts omit the action. Storage failures, invalid time-provider
facts and unexpected conflicts propagate through the existing read-failure boundary. They do
not become evidence that an action is available. Other scheduling controls and saved original
requests retain their existing behavior.

`tests/backend/test_fixed_skip_discovery.py` checks genuine settlement and original recovery,
available/assigned eligibility, strict instant and local-date boundaries, started/blocked/
cancelled/completed work, performed-then-reopened work, rescheduled deadlines, current
authority and unavailable facts. The protected HTTP journey in
`tests/backend/test_recurrence_http.py` now reads the settled target in both entry modes and
requires the repeated skip option to be absent. Existing preview/apply tests keep their
current-fact, competing-change, retry, rollback and restoration assertions.

The new journey in `frontend/tests/e2e/tasks.spec.ts` covers Ingress and standalone, English
keyboard and Spanish narrow touch. It uses the existing genuine calendar fixture, explicitly
enables the policy, checks completed/started/future targets, claims one eligible overdue task
and requests one reviewed skip. It requires fresh targets to omit the repeated action,
preserves an unrelated creation draft, compares all unaffected task records, recovers the
same original receipt and checks facts again after runtime restart. These are qualification
assertions; collection alone does not establish that the journey has passed.

The collected source inventory grows from 161 to 165 journeys. The actual-image inventory
grows from 106 to 110 per architecture; its CI gate still rejects unexpected, skipped or flaky
results. The exact Action versions, self-hosted placement and published ha-ui cohort remain
unchanged. The Domus review form gives its grid column a zero minimum so native controls
remain inside the scheduling card on narrow screens.

The full local backend campaign passes 6,066 tests, with 100% line/branch coverage globally
and for every one of the 250 Python files. The initial full-suite invocation had a missing
temporary-directory parent; its setup errors and partial reports are retained separately.
The corrected command passes the independent per-file source audit. Four genuine source
browser variants also pass after waiting for the seeded task list before opening the draft;
the initial preparation timeout remains recorded. The narrow-layout correction passes all four
source variants independently. The full 2,287-test frontend campaign retains 100% supported
coverage globally and per file across 114 nonempty and seven empty runtime files. Current
typing, application import contracts, 238 architecture/Python-tooling tests and documentation
checks pass.

Complete final-head CI/review, normal merge and destination acceptance remain separate
open gates for this increment. Full M2, the remaining roadmap and Stable/distribution
acceptance remain open independently.

The prepared Edge.93 declaration pins runtime `72c241b`, schema 37 and the exact ha-ui
`0.1.0-next.5` cohort. The official source archive matches all 1,039 tracked Git blobs.
All 250 Python and four compiled UI wheel files match the verified source and current
source-browser payload; only the three intended Python modules differ from Edge.92.
This inventory proof does not substitute for actual pinned-image or installed acceptance.

The actual immutable ARM64 Edge.93 image passes the three selected package/runtime contracts:
all 250 Python/four UI files match the declaration, native launcher authority/storage/replay/
restart, and standalone exact private-bundle delivery. All four selected Chromium journeys
also pass against that image. These bounded runs do not replace the full both-CPU CI inventory.

The installed Home Assistant candidate passes English desktop keyboard and Spanish 390px
mobile touch acceptance. A real four-occurrence schedule supplies completed, performed-then-
reopened, started and future work whose fresh review menus omit the action. One eligible
assigned overdue occurrence is explicitly previewed and skipped. The other three task
projections and an unrelated draft remain unchanged. The same original receipt is recovered
before and after the public stop/start controls; all four task projections survive restart,
and the settled action remains absent. Served JS/CSS match the pin. The installation finishes
stopped with all four optional switches off. No native fixture or private API writes are used.
The initial required-origin configuration and an owner-environment HA restart are recorded
separately from acceptance. Debugger events were evicted during the full HA shell reload;
direct current reads and original receipts were retained afterward. This is not a gapless
HTTP trace or an installed per-file Python-hash claim.

## Browser response observation follow-up (2026-11-28)

The current destination check at `73fb99355b4e0835ca1db3329bd5041f8430061e`
exposed a remaining observation-lifetime failure in this journey's `openReview`
helper. The first source run passed 172 of 173 journeys and the first ARM64 image
run passed 117 of 118. The unchanged source retry again failed this helper in
native-English and standalone-English variants. All target requests observed in
the retained failure traces returned 200; the rendered review form was present.
Chromium rejected `Response.json()` with `Network.getResponseBody: No data found
for resource with given identifier`. The available trace does not establish the
underlying cancellation trigger. Original reports, screenshots and traces remain
separate from successful execution evidence.

The correction uses the actual-byte pattern already accepted by
[issue #148](https://github.com/vypdev/domus/issues/148). For each selected target,
it owns only the exact GET route, performs one real upstream fetch with zero
retries and zero redirects, retains its raw JSON bytes and delivers the unchanged
response to the application. The browser status and ready form are checked, and
exactly one captured target is required. The owned route is removed in `finally`.
The existing protected-target, policy, single-skip, current-record, draft,
original-receipt and restart assertions remain intact. This extends the existing
recurrence-calendar-C30 witness without adding or renumbering an owning case.

Local source qualification passes all four entry-mode/locale scenarios and then
40 consecutive executions, ten of each scenario. Every execution passes once at
retry zero, with no skipped, unexpected or flaky results. All 280 actual target
response bodies, seven per execution, are retained before unchanged delivery.
The source runtime and four rebuilt UI assets match the already qualified Edge.95
wheel.
The local results qualify the test-observation correction. Complete final-head
CI and substantive review, normal merge and exact destination validation remain
required. The
current 173 source, 118 per-image and 70 catalog case inventories, deadlines,
zero-retry policy, coverage gates, exact Actions tags and self-hosted placement
are retained. Edge.95 runtime/packaging and its installed private data require no
change for this observation correction. Full roadmap and distribution acceptance
remain independent gates.
