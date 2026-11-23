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

Immutable package/image acceptance,
installed Home Assistant observations and final-head CI/review remain separate open gates
for this increment. Full M2, the remaining roadmap and Stable/distribution acceptance remain
open independently.
