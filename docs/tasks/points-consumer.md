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
use the frozen shares for new completions. Older pending cycles use their
original conserved calculation. The report shows the four most recent pending
allocations with their exact shares and stage. Pending totals cover all matching
work in the selected period. Available points come from posted entries. Posted and available values coincide before reward
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

## Configured allocation

Household defaults and task-definition overrides are changed through the protected
allocation settings routes. Current `points.manage` authority is required to
read or change settings and to supply manual shares. A task override takes
precedence. Clearing it preserves its revision while subsequent completions
inherit the household default. For previously unconfigured households, the
legacy conserved split still uses fractional precision when the base requires it.
The initial explicit setting is a whole-point conserved split.

The preview uses the current task revision, selected active members, exact
minor units, and the same allocation engine as completion. The browser sends
the reviewed fingerprint when recording work. The completion transaction
rejects a stale fingerprint and saves a new cycle and its allocation together.
Conserved splits advance their position when the cycle is recorded. Approval,
posting, retries, and reversals use the stored shares and do not advance it.
History shows the original policy, rounding, revision, and award total.

Schema 18 adds scoped settings and frozen allocations. An interrupted migration
leaves schema 17 intact. Older cycles and ledger rows remain readable using
their original conserved behavior. Checkpoint inspection validates stored policies,
shares, source cycles, and the retained remainder sequence. Restore preserves
the selected settings and allocations. A later settings request is recoverable
as historical by its original key.

[Allocation HTTP tests](../../tests/backend/test_point_allocation_http.py) exercise
current authorization, configuration revisions, stale previews, pending approval,
and linked reversals in both deployments. [Storage tests](../../tests/backend/test_point_allocation_storage.py)
exercise a real [schema-17 database](../../tests/fixtures/sqlite/v17-allocation-source.sql),
interrupted migration, simultaneous completion replay, restart, and corrupted
evidence. The [Points restoration test](../../tests/backend/test_points_consumer.py)
uses a real activated checkpoint with an existing configured award.

| Issue #64 evidence | Observable case |
| --- | --- |
| `family-allocation-C01` | Pure exact allocation tests for conserved, equal, full, and manual shares, both precisions, the performer limit, and bounded values. |
| `family-allocation-C02` | Both composed HTTP paths reject unauthorized settings and manual shares, inactive or duplicate participants, and injected policy. |
| `family-allocation-C03` | The HTTP cycle keeps its frozen policy through override edits, approval, replay, and reversal. Clearing the override changes the next preview. |
| `family-allocation-C04` | SQLite tests exercise concurrent completion replay, transaction rollback, restart, exact reversal, and restoration of prior policy and shares. |
| `family-allocation-C05` | The compiled Chromium workspace checks the policy editor, localized exact preview, and posted history in Ingress and standalone. |
