# Points consumer for task lifecycle events

This implementation note accompanies the [Points owner specification](../../specs/points-rewards.md)
and [issue #56](https://github.com/vypdev/domus/issues/56).

Ingress and standalone each run a local Points worker against the existing installation
and household. A pass reads at most 25 original task lifecycle events in source order.
The worker saves each receipt and any posting in the same SQLite writer transaction.
A cycle can have one allocation and one reversal. The internal integration query
reads at most those two postings for an exact household and cycle. It is not an HTTP route.

Eligibility comes from the authenticated completion or approval, its immutable rule
snapshot, and the current cycle in the same transaction. A restored historical
rejection or reopening fences an unposted cycle. Historical operations never create a
new movement in the ledger. A reopening reverses the stored shares of its own cycle.
It does not recompute them or affect another cycle.

The initial policy is `conserve_total.v1`. Whole-point values split in whole-point
quanta. Previously supported fractional values use minor-unit precision so no
credit is rounded away. The next remainder recipient is stored with the allocation.
Participants are ordered by stable member ID. When a member is absent, rotation
resumes at the first current ID at or after the saved position and wraps as needed.
A split with no remainder and a reversal leave the position unchanged.

Schema 16 adds the Points receipt table and its indexes. The migration creates
no credits. Startup processes eligible live events and records pending ones without
awarding them. Checkpoint inspection validates the original source and recomputes
each award and linked reversal. The [schema-15 fixture](../../tests/fixtures/sqlite/v15-points-source.sql)
was captured from develop `870ab5437a510ae419961bf695706021d2efd56d` with two original
task completions. Its SHA-256 is `49522d9ca92a55dbe6a751c768ab17250c93010a7ceb6fce4dc6331d2c4f5e45`.

[Consumer tests](../../tests/backend/test_points_consumer.py) cover the schema fixture,
the real recurrence and Points interaction, worker composition, concurrency,
rollback, restart, and restoration. The combined Inventory assertions retain
their original acceptance identities in [issue #23](https://github.com/vypdev/domus/issues/23).


## Family read model

The protected `GET /api/v1/family` endpoint uses the same context assertion and
current household permissions on Ingress and standalone. The server selects the
member from the verified session. The response includes signed history in posting
order and a cursor bound to the member, their current authority, and the requested
report. The Points worker remains the writer of awards and linked reversals.

The selected week or month reports actual work in the household zone. Approval
and posting keep their own timestamps. Pending verification and pending posting
show estimates from the current conserved split and rotation. Available points
come from posted entries. Posted and available values coincide before reward
reservations are introduced.

Recorded completions remain visible after reopening. A reversal corrects the
original period's earned points without erasing the work or posting history.
Elapsed time is measured from the last recorded transition into progress before
completion in the same occurrence cycle. It estimates the elapsed interval and
may include pauses. Family identifies how many completions have a recorded start.

[Family HTTP tests](../../tests/backend/test_family_http.py) use both deployment
compositions, real SQLite and the Points worker for scoped reads, the Sunday and
month-end transition, cursor binding, and restart. The restore case checks an
actual activated snapshot and suppresses duplicate postings. The
[workspace browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts)
covers localized history and the Points worker in the same protected workspace.
