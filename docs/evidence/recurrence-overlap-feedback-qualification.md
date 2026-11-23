# Retained-work overlap feedback

Domus issue [#173](https://github.com/vypdev/domus/issues/173) supplements the
existing recurrence-calendar-R5/C34 witness with recoverable preview feedback.
It creates no new owning requirements or cases and does not change domain
collision policy. The bounded source/package receipt is
[recurrence-overlap-feedback.json](recurrence-overlap-feedback.json).

Only a validated failure envelope with HTTP 409, the exact
`recurrence_reschedule_collision` code and a preview POST maps to the application
category `overlap`. Authorization failures, other validated codes and apply
rejections remain generic. Malformed or uncertain posted replies retain original
request recovery. A failed CSRF read cannot claim a preview collision; neither
can an original-request GET. Arbitrary server prose is never displayed.

The English and Spanish notice explains that no change was made and asks the
manager to change the dates or pattern and preview again. The original date,
time, pattern and reason remain available. A rejected preview has no apply
action. Journal persistence failure takes precedence, and retired ownership
cannot publish a late result.

A newly submitted collision receives focus and follows dependent layout changes
only while it owns focus. Newer keyboard, pointer, wheel, input or focus changes
take over. Closing, read-only access, detachment and removal retire the pending
focus. A fast reply can coalesce the busy and settled renders without losing
the initiating preview's focus ownership.

`frontend/tests/recurrence-review.test.ts` covers the strict transport matrix,
application recovery and component draft/focus behavior. The complete frontend
unit campaign passes 2,279 tests with all four coverage metrics at 100% globally
and in every nonempty runtime file: 114 nonempty files and seven empty files.
Runtime/catalog type checks, 42 Node policy tests, 187 Python tooling tests,
51 Python architecture tests and 68 catalog variants also pass.

The genuine occupied-date journeys in `frontend/tests/e2e/tasks.spec.ts` use the
existing calendar fixture and the actual protected application. Ingress and
standalone each run English keyboard and Spanish 390 px touch. Two deliberately
conflicting previews return real 409 responses, focus visible localized guidance,
retain the latest proposal and leave every task unchanged. Correcting the date
permits one explicit apply. Started and completed work remain byte-for-byte equal
in public task projections; the selected eligible occurrence is cancelled.
Original GET recovery and runtime restart return the same receipt and task facts.
Standalone reauthenticates after restart, matching its non-durable session boundary.

The actual-image inventory increases from 102 to 106 journeys per architecture,
with zero unexpected, skipped or flaky results required. Complete source-browser,
image, installed Home Assistant and final-head CI/review results remain separate
gates; a source unit result does not substitute for them. The immutable Edge.90
candidate preserves schema 37, all 250 Python product files and the exact
`0.1.0-next.5` ha-ui cohort. Prior qualification receipts remain frozen.

The local ARM64 candidate passes all three selected exact-package, native
authority/storage/restart and standalone-bundle checks. Its four occupied-date
image journeys also pass with zero unexpected, skipped or flaky results. The
legacy Edge.5 upgrade is deliberately left to the complete final-head container
matrix, rather than claimed from those three local checks.

The initial complete local entry campaign passes 160 journeys; one new native
English test cannot retrieve a response body through Chromium's DevTools
interface. Its original report, trace and screenshot are retained. The corrected
observer forwards the real upstream response once with zero retries and inspects
that retained response, preserving every collision/draft/apply assertion. All
four corrected source and all four actual-image variants pass. The complete
161-journey final-head CI gate remains required; this receipt does not represent
the initial local campaign as fully green.
