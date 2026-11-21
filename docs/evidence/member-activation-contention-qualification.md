# Member activation contention qualification

[Domus #152](https://github.com/vypdev/domus/issues/152) also qualifies the
existing direct member-activation observer exposed by the first full CI after
the [manual automation correction](automation-execution-qualification.md#temporary-storage-contention).
The existing administration contract retains explicit authorized activation and
original-request recovery under `HADM-03` and `HADM-05` in the
[owning specification](../../specs/household-administration.md).

On source `0686c6216710610869367c2a45b7ba82a20f984b`, the
[original backend job](https://github.com/vypdev/domus/actions/runs/44867897376/job/136735599143)
finished with 5,646 passed tests and one failure in 1,803.72 seconds. All ten
automation race cases passed. The remaining failure was the concurrent identical
activation in [the member command tests](../../tests/backend/test_member_commands.py):
it required two immediate receipts, while one real competing command raised the
documented `StorageBusy`. The original log and coverage are retained. Coverage
was 100% across 231 runtime modules; the failed suite remains unaccepted.

The member test retains its original unrestricted race and adds a held-writer
case. Both administrator commands complete their original identity-proof barrier.
One then holds its real SQLite receipt transaction until the competing call
finishes, exercising the actual 250 ms busy timeout. The callback stores the real
receipt before waiting; it does not fabricate a response or raise a mock error.

Both cases require exactly one activated member at revision 2 with the requested
role and retained identity, the same original receipt and fingerprint, one added
audit entry and one added pending event with that operation ID. Previous members,
policy, audit and pending events remain intact. Only a typed `storage_busy` may be
observed temporarily. After both calls finish, one explicit retry with the same
frozen command key and request must return the exact accepted receipt without any
further effect. A changed payload under that key still conflicts. The existing
receipt equality and final effect-count assertions remain active.

The controlled old-oracle reproduction failed the held-writer case and passed
the unrestricted case. The corrected pair passed both cases. The complete member
and automation command files plus the existing storage-contention HTTP tests
passed all 77 cases. This is direct-command evidence; it does not replace the
complete product CI, current-head review, both deployment and CPU image gates,
or exact destination qualification after a normal merge.

Application files, SQLite timeout, automatic retry behavior, workflow budgets,
schema and specification ownership are unchanged. The immutable Edge.70 runtime
is reused only after verifying its 231 Python and four compiled UI file hashes.
