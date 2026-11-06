# Review a manual task for relative recurrence

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
