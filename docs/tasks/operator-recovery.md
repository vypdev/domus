# Task operations and recovery

This guide describes the development task backend in both native and standalone compositions.
The product task UI and real Inventory/Points consumers remain incomplete. Installed Edge.3 is an
independent immutable M1 package; this guide does not claim it contains the new task source.
Use the [API contract](execution.md) for request fields and permission requirements.

## Diagnose before requesting new work

Keep the original command payload, Idempotency-Key and returned operation ID. Read the occurrence,
its cycle, material intents and history with a currently authorized account. Assignment, actual
performers, recording actor, performed time and approval time are different facts. A receipt is an
immutable original result, not a current-state view.

If a response is lost after commit, deliberately recover with the same payload/key. The server checks
current authority before revealing the old result. A revoked grant, inactive account or suspension
does not become authority because a receipt exists. Do not replace an uncertain key or silently
rebase a stale revision. Read actual state before deciding on a new operation.

Task operation lookup is under /api/v1/tasks/operations, separate from household-administration
operation lookup. History pages distinguish current effects from retained operations restored away.
Generic delivery acknowledgement does not prove Points, Inventory or recurrence consumed an event.
The internal typed lifecycle feed never confirms those consumer effects.

## Verification and reopening

Pending or rejected restricted-member work has no confirmed Points award. A current authorized adult
may verify under the cycle's snapshotted approval policy. Approval does not close the cycle or move
its performed time. Reopening explicitly names that cycle and a meaningful reason, closes it and
retains the original work history. It does not return physical supplies automatically.

Completed dependent work is not reopened in a cascade. Its dependency-review page shows the original
source reopening, current source state and whether the original dependency gate is satisfied. A
current task manager may accept that one cause with a meaningful reason while the prerequisite is
still pending. Acceptance retains reviewer, time and reason; it never hides the prerequisite state.
A later reopening has a separate cause and cannot reuse the old acceptance.

## Materials and explicit follow-up

Work can remain completed while a material intent needs processing, authorization or stock
regularization. Unknown actual use, explicit zero, separately recorded use and confirmed consumption
are distinct. Missing Inventory never creates a movement or negative stock. The current default
composition has no real Inventory provider; nonempty linking fails safely and valid work may retain
truthful pending usage. An approval or later stock/grant change never settles it automatically.

An authorized participant may explicitly post, correct or dismiss the original cycle/intent using
its current intent revision. A correction submits a new desired total and a meaningful reason;
dismissal also needs a reason. The API retains the last confirmed quantity/effect/time separately
from a desired pending correction. A36 permits confirmed corrections by currently authorized material
participants. Do not interpret a queued correction as an already reversed movement.

## Unavailable HA, contention and corruption

An existing unexpired session may read permitted local facts during a temporary HA outage. Changes
wait for fresh verification; explicit HA rejection ends access. Do not add another account, weaken
Ingress/session guards or supply a technical credential as human authority.

A bounded storage lock or stale revision needs inspection and an explicit retry of the original
operation, not a new key. Invalid paired receipt/audit/outbox evidence fails closed. Preserve owned
database and operation references for diagnosis; never repair them with direct SQL or manufacture
acknowledgements. Safe correlation and operation IDs are sufficient for ordinary reports; exclude
credentials and raw canonical requests.

## Snapshot, restore and rollback

Follow [manual snapshots](../snapshots.md), [offline restoration](../restoration.md) and
[task migration](migration.md). Restore selects checkpoint state and retains readable later receipts
as already processed. A historical result whose effect is absent must not be replayed into current
state. Inspect current work before deliberately requesting genuinely new work.

Keep installation/channel identity, the exact compatible application and its paired data together.
Do not decrement a schema version or switch generation pointers manually. Stop the runtime for the
documented activation/resume flow, use the same restore ID after uncertainty and preserve diagnostic
partial output. These source/real-file protocols do not claim live owner restoration or package
adoption. The full first release still requires all domains, both targets and isolated channels.
