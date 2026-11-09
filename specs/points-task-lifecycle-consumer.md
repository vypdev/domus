# Points consumer for task lifecycle events

This implementation note accompanies the [Points owner specification](points-rewards.md)
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
each award and linked reversal. The [schema-15 fixture](../tests/fixtures/sqlite/v15-points-source.sql)
was captured from develop `870ab5437a510ae419961bf695706021d2efd56d` with two original
task completions. Its SHA-256 is `49522d9ca92a55dbe6a751c768ab17250c93010a7ceb6fce4dc6331d2c4f5e45`.

[Consumer tests](../tests/backend/test_points_consumer.py) cover the schema fixture,
the real recurrence and Points interaction, worker composition, concurrency,
rollback, restart, and restoration. The combined Inventory assertions retain
their original acceptance identities in [issue #23](https://github.com/vypdev/domus/issues/23).
