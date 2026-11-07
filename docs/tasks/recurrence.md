# Review a manual task for relative recurrence

## Review scheduling from Tasks

Select a task in **Tasks**, then open **Review scheduling**. Domus loads the current rule and
task revisions and offers the applicable choices to members who can manage tasks. Enter the
local date, optional time or other details for the selected change. **Preview schedule change**
shows the impact before **Apply reviewed change** confirms the exact selection. A preview expires
after five minutes. Review the current rule again if the plan expires or a concurrent change
makes it stale.

If a response is lost, open **Saved schedule requests** and choose **Check original schedule
request**. This reads the original operation without sending another change. A recovered
historical receipt means the operation was processed before a restore and the effect is absent
from the current generation. Saved requests are scoped to the verified household member in
this browser tab. The registry holds eight requests for one hour from their original creation.


A relative schedule with an unconsumed first slot waits when its task definition already has manual
work. A household task manager can select one compatible occurrence and review its exact schedule
and task revisions. The review shows the task and due date that will be retained. Applying it binds
that same task to the initial slot and preserves its identity, assignment, due date, and history.

The occurrence must still be available or assigned with complete evidence that work has never
started. It must match the current active task definition and the schedule's initial due value.
If the task, rule, or reviewer context changes, request a fresh review. A review expires after five
minutes. A restored historical preview cannot authorize a new change.

Both [Ingress](../contracts/native-household-api.openapi.json) and
[standalone](../contracts/household-api.openapi.json) expose the protected review API under
`/api/v1/tasks/recurrence/reviews`. Send the verified `X-Domus-Context` on every request, and the
session's CSRF token, Origin, and a unique Idempotency-Key on each write.

1. Submit `POST /adoption/preview` with the schedule and occurrence IDs and their current revisions.
2. Inspect the returned plan. Submit `POST /adoption/apply` with the same selection, the original
   preview key, and the returned plan fingerprint. Use a separate idempotency key for this apply.
3. If a response is lost, look up `GET /requests/{action}/{key}` using the original key and the
   corresponding action `recurrence.review.preview` or `recurrence.review.apply`. A historical
   apply receipt records a previously processed operation whose effect is absent from current
   state. Inspect current state before choosing further work.

## Pause and resume a relative schedule

Use `POST /state/preview` with the current schedule ID and revision. Set `target` to `paused` to
stop generation or `active` to resume. Inspect the retained work and backlog. Apply the reviewed
state through `POST /state/apply` with the same selection, original preview key, and fingerprint.

Pause preserves assignments and existing task history. A completion observed while paused can
still supply the next date after resume. The preview derives that date from the original performed
time and schedule policy. Pending verification, a closed cycle, manual work requiring adoption, and
historical absent effects have separate backlog statuses. Resuming saves the rule state. The owned
maintenance runner processes the backlog and preserves the due date even when it is overdue.

## Skip an overdue fixed slot

Review a specific materialized fixed slot through `POST /fixed-skip/preview`. Supply the current
schedule and occurrence IDs and revisions, the original slot key, and a reason. A date-only slot
becomes overdue after its nominal date in the slot's saved time zone. A timed slot becomes overdue
after its saved due instant. Only available or assigned work with a proven unstarted history can
be skipped.

Apply through `POST /fixed-skip/apply` with the original selection, preview key, and fingerprint.
The skipped task keeps its original slot and reason. Future fixed slots continue from their
existing schedule. The operation records the original actor and transition without recording a
completion or awarding points.

## Attach a relative rule to an existing task

Use `POST /attachment/preview` with the definition and occurrence IDs and revisions, the initial
nominal date or local time, the interval in local days, the time zone and the attachment choice.
An active task definition can have one current recurrence rule. The preview resolves the initial
time with the packaged time-zone data and records the exact manual work under review.

- Choose `adopt` to use an available or assigned occurrence with a proven unstarted history as
  the first recurring obligation. A timed initial slot must resolve to the occurrence's existing
  due instant. An untimed occurrence can adopt a date-only slot.
- Choose `retain_manual` to keep the occurrence independent. The reviewed first recurring
  obligation must be separate from all open manual work on the definition. With open manual
  work, Domus requires a timed first recurring due date after every known manual deadline.
  A date-only first recurring slot is available when the existing work is closed.

Apply with `POST /attachment/apply`, the same selection, the original preview key and its plan
fingerprint. If the task, reviewed backlog, or time-zone facts change, refresh the preview. The
rule, the first recurring obligation and the original receipt commit together.

## Review relative successor settings

Use `POST /relative-settings/preview` with the current schedule ID and revision, the interval in
local days and successor visibility. The preview identifies the retained initial timing and
current occurrence. Changes affect future successors. Already issued task identities, assignments,
and deadlines are preserved. A current unclosed completion or an absent restored obligation
requires reconciliation before editing so that the rule never reinterprets an earlier effect.

Apply through `POST /relative-settings/apply` with the original selection, preview key, and
fingerprint. Domus saves the updated rule revision and binds its progress to the original
operation in the same transaction.

## Move an unstarted scheduled occurrence

Use `POST /reschedule/preview` with the schedule and task IDs and revisions, the original slot
key, the destination in the same nominal kind, and a reason. Domus resolves a timed destination
under the original slot's saved time policy. The preview shows the original slot, current
deadline and new deadline. An occupied destination or a fixed nominal slot belonging to another
obligation requires a different choice.

Apply through `POST /reschedule/apply` with the original selection, preview key, and fingerprint.
The task keeps its identity and assignments. Task history records the reason and destination.
The original recurrence slot stays available as planned history. A later reviewed skip uses the
effective deadline.

## Pause and resume a fixed schedule

Use `POST /fixed-state/preview` with the schedule ID and current revision. A pause retains open
work, its assignments, and the existing recurrence cursor. A resume previews the pending
nominal slots through the current local day and the open work that will be retained. If the
complete plan exceeds the review bound or contains coincident instants, Domus blocks the change
and keeps the rule paused.

Apply through `POST /fixed-state/apply` with the original selection, preview key, and
fingerprint. The maintenance runner continues from the same cursor after resume.

## Review a prospective fixed pattern

Use `POST /fixed-pattern/preview` with the schedule ID and revision, a new nominal start, and
the supported RRULE. Domus previews the new pattern for 60 local days and retains all issued
work and explicit exceptions. The new start must be beyond existing original slot history
and active rescheduled deadlines. A change that would replace issued work requires a separate
replacement review.

Apply through `POST /fixed-pattern/apply` with the original selection, preview key, and
fingerprint. The new pattern gets an independent continuation. The old slots and receipts
remain inspectable.


## Replace future fixed work in a batch

Select an occurrence from the fixed schedule and open **Replace future fixed work in a batch**.
Supply the new local start, RRULE and reason. The preview lists retained work, occurrences
that will be cancelled, and the dates of linked replacements and new pattern slots. The
current rule must be active. The plan covers a bounded 60-day horizon starting on the
requested local date. If affected work or a moved deadline falls beyond it, review a later
start or resolve that work individually.

The original occurrences remain in task history with the cancellation reason. Domus pairs
matching nominal dates first, then pairs the remaining eligible work in chronological
order. A replacement inherits compatible assignments. Started or completed work and
previous individual changes remain visible. If a deadline collides with that retained
work, a live dependency would be broken, or an assignment has no compatible destination,
the batch is rejected so the manager can review the current facts.

The rule revision, original cancellations, replacement work, new slots and continuation
commit together. Use the original request to recover the linked result after a lost reply.
A restored-away result remains historical.
