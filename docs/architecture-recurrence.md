# Recurrence architecture and implementation evidence

## Temporal checkpoint

The first source checkpoint implements immutable [temporal facts](../backend/src/domus/domain/recurrence_time.py),
the [semantic application port](../backend/src/domus/application/recurrence_ports.py), and a
[pinned timezone adapter](../backend/src/domus/infrastructure/recurrence_time.py). These establish
neither scheduling authority nor a running recurrence service. Existing task APIs and the installed
Edge.5 application do not invoke them.

A nominal time is a naive local Gregorian value from 1970 through 9999, with at most millisecond
precision and no implicit fold selection. A resolved fact retains that nominal value, the actual
local value, integer UTC milliseconds, offset seconds, resolution reason, policy revision, explicit
timezone-data identity and SHA-256 of the actual zone bytes. Invalid precision, implicit zones,
inconsistent fold policy, negative UTC time and conversion overflow fail explicitly. Fixed-rule
minute precision will be enforced by the future schedule contract; completion-relative work retains
its original milliseconds.

Domus uses the hash-locked `tzdata==2026.6` package (IANA 2026f). The adapter checks the installed
package and IANA identities and reads bounded packaged catalog/TZif data. It constructs
`ZoneInfo.from_file` from those bytes; it does not consult or change the process-global timezone
path or cache. Unknown keys, unavailable resources, corrupt resources and incompatible versions
have separate safe errors. The zone bytes and policy identity remain facts for later persistence.
See the [Python ZoneInfo source contract](https://docs.python.org/3.14/library/zoneinfo.html).

Round-trip UTC conversion establishes whether a nominal wall time exists before selecting an
appearance. An ordinary time has one instant. A fold selects one of its two actual instants, first
by default or second under the explicit policy. A gap uses the forward TZif round-trip as the upper
bound of that gap, then searches integer milliseconds for its first valid boundary. This is at most
28 probes for the supported 48-hour bound. Madrid 02:30 becomes 03:00; Lord Howe 02:15 becomes
02:30. Historical second-resolution offsets remain supported. A wholly missing Apia date advances
to the next first valid instant, retaining its original nominal value; another nominal slot at the
same instant remains distinct. Later materialization must preserve their keys and expose collision
review rather than deduplicate them by UTC time.

Completion-relative conversion starts from actual performed-at UTC milliseconds, converts to the
snapshotted local zone, adds the configured integer local calendar days, then applies the same
resolver. A day across the spring or autumn transition can be 23 or 25 elapsed hours. Approval time
is not an input. Lifecycle visibility, cycle closure and durable successor uniqueness remain to
implement in their owning application service.

The architecture policy explicitly rejects `zoneinfo`, `tzdata`, `dateutil` and resource/metadata
loading in domain/application modules. Real disposable negative import graphs exercise both inner
layers. The implementation, tests and verification limits are recorded in
[checkpoint evidence](evidence/recurrence-execution.json).

At this temporal checkpoint, rule parsing/expansion, task classification, schema 8, durable
materialization, source consumption, preview/apply, calendar queries, the composed runner and actual
image/browser/HA acceptance remained outstanding. All 52 companion cases and 37 original owning
cases remained requirements. The later checkpoints below record subsequent source progress;
this original evidence does not establish a shipped package or the first all-domain release.

## Bounded rule and planning checkpoint

[Closed patterns](../backend/src/domus/domain/recurrence_rules.py) and their
[strict text parser](../backend/src/domus/domain/recurrence_rule_text.py) validate the declared
DAILY/WEEKLY/MONTHLY/YEARLY subset before expansion. Duplicate parts/selectors, COUNT plus UNTIL,
unsupported frequencies/parts, malformed Gregorian values and incompatible selector combinations
fail explicitly. Date-only and minute-precision starts are tagged separately; all defaults are
explicit and unordered selectors normalize to the same pattern fingerprint.

The [period policy](../backend/src/domus/domain/recurrence_periods.py) computes an indexed original
frequency period directly, preserving interval phase and week start.
[Nominal expansion](../backend/src/domus/domain/nominal_recurrence.py) examines at most 366 dates,
including a period with an impossible selector. Invalid month days are omitted. Ordinal weekdays
use their month/year scope, a mixed BYDAY list is a union, and BYSETPOS selects from the whole
frequency period before DTSTART trimming. Fixed dates keep their original anchor across empty
months, leap years and restart.

This explicit bound is deliberate. A retained dateutil4.0.0 control requested only February2026
with a February30 selector, but reached 65 internal monthly rebuilds through June2031 without one
candidate before the observer stopped it. UNTIL and a limit on yielded values do not prove bounded
internal traversal. Domus does not install that unused library or its stubs. This measured adapter
decision does not change the supported product subset or the separate pinned timezone contract.

The [application planner](../backend/src/domus/application/fixed_recurrence.py) composes the nominal
and temporal ports. It preserves period index, offset and nominal count in a validated
[continuation](../backend/src/domus/domain/recurrence_planning.py) bound to the canonical pattern
and complete time-policy snapshot. It rejects a changed binding, inconsistent source result or
out-of-range progress. Slot and period budgets are independently bounded. A half-open nominal
horizon leaves its next slot unconsumed; an incomplete scan remains visibly incomplete. COUNT and
inclusive UNTIL retain their original meaning across batches. A start preflight reports its first
permitted candidate or explicitly incomplete search without rewriting DTSTART.

These are planning facts, not durable execution proof or permission. Nominal counts are computed
before future exception filtering; explicit exception/addition provenance, receipt/slot uniqueness,
historical restore non-recreation and atomic persistence remain required. The current cursor is
not exposed as a public authorization token. No scheduled task is created by this checkpoint.
See [rule/planning evidence](evidence/recurrence-rules.json) for measured results and remaining scope.

## Owned fixed-recurrence storage

The current [records](../backend/src/domus/domain/recurrence_records.py) remain pure immutable
facts. A record constructor grants no human or technical authority. Rule record revisions support
compare-and-swap updates. A separate pattern revision changes only when the pattern or time policy
changes, so a pause does not invent a new nominal obligation. Cursor binding includes the complete
canonical pattern and time-policy snapshot.

The [repository port](../backend/src/domus/application/recurrence_ports.py) is part of the existing
unit of work. Its [SQLite adapter](../backend/src/domus/infrastructure/sqlite_recurrence.py) never
commits independently. Schema 8 stores rules, matching progress and immutable nominal slots with
scoped definition/occurrence relationships. Deferred constraints require matching rule/progress
pattern revisions and the exact slot command receipt before commit. A failed partial update leaves
all prior rows intact; previous slot snapshots survive a valid pattern/progress replacement.

A slot key hashes installation, channel, household, schedule, pattern revision and the tagged
nominal value. It is independent of the task identifier and mutable record revision. The technical
command namespace is fixed. It does not create a current human identity or bypass future runner
authorization. Receipt, audit and outbox records still share the existing atomic transaction.

[Closed versioned codecs](../backend/src/domus/infrastructure/sqlite_recurrence_records.py) reject
unknown fields/versions, duplicate JSON keys, noncanonical date/time tags and corrupt header/body
bindings. Date-only records retain dates without a fabricated UTC midnight. The existing canonical
JSON byte bound applies. Snapshot inspection additionally verifies current source/cursor binding,
installation scope and the slot/occurrence identifiers in original receipt results. It rejects
progress above the configured count, future slot generations and contradictory snapshots in the
same generation. Legitimate older generations remain valid after edits. Incomplete or inconsistent
records are rejected without rewriting their source.

The pure [membership check](../backend/src/domus/domain/recurrence_membership.py) also verifies that
the nominal is a real candidate of the original pattern and fits COUNT/UNTIL. Matching headers and
an exact receipt cannot turn an arbitrary date into scheduled work. COUNT uses actual nominal rank,
including omitted invalid dates and the truncated initial period. Gregorian cycles preserve the
original interval phase and bound distant rank calculation; bounded memoization only avoids
recomputing pure period counts. Constructor, closed decoding and checkpoint inspection share this
invariant. A corrupt current or historical slot is rejected rather than silently reinterpreted.

The [migration guide](tasks/migration.md) distinguishes current source schema 8 from the immutable
installed Edge.5 schema 7. CI builds a separate checked-out-source image for both CPU architectures
and retains Edge.5 as a genuine old-image compatibility control. Its version is ci-current and it
has no publication/deployment step. Actual hosted build/test outcomes remain required evidence.

These are repository and migration capabilities. Actual fixed/relative materialization, lifecycle
consumption, restore non-recreation, preview/apply, protected calendar queries and composed runners
remain unfinished. The four additional storage refinements do not
recount the retained 52 companion or 37 original owner cases. See
[storage evidence](evidence/recurrence-storage.json) for exact tests and acceptance limits.

## Authorized new fixed-task creation

The application [creation command](../backend/src/domus/application/recurrence_commands.py) validates
new active fixed tasks with current HA proof and the existing task-create, privileged override and
inventory-link permissions. It shares [task definition creation](../backend/src/domus/application/task_creation.py)
with the ordinary manual path. A definition, rule, unconsumed progress and original receipt/audit/outbox
commit together. Manual creation retains its one initial occurrence; scheduled creation creates none
until real materialization, so validation cannot consume or duplicate its first obligation.

Pinned zone/data validation and bounded DTSTART preflight occur outside the writer transaction,
including for date-only rules. The command returns an authorized original receipt before provider
work and checks current local grants again before new writes. A rejected/unresolved start is not
silently moved. The result explicitly reports pending processing and no first occurrence; it does
not imply runner execution, task performance, points, inventory consumption or downstream delivery.

This is an application use case, with no new public route or deployed interface yet. Draft/relative
configuration, reviewed attachment, protected operation recovery queries and full runtime/HA
acceptance remain required. See [creation evidence](evidence/recurrence-creation.json).

## One fixed-materialization step

The application [maintenance step](../backend/src/domus/application/fixed_materialization.py) receives
an explicit local installation/channel/household scope from trusted composition. It accepts no
human actor or authority from a rule or HTTP body. An active source can create at most one real
occurrence, or advance through at most 64 empty original periods. Inactive rules/definitions retain
their current work. Policy lookup and planning occur outside the writer transaction; source revisions
and the narrow technical command namespace are checked again before reading original receipts.

The shared [command boundary](../backend/src/domus/application/commands.py) can join that same
caller-owned transaction without committing independently. New task/slot/progress and original
receipt/audit/outbox commit or roll back together. A current original receipt advances a replayed
cursor without another effect. An actual restored-away slot returns its original historical receipt
and advances only the reconciled cursor; it creates no replacement task, identities or duplicate
event. Contradictory current effects, corrupted original results and changed payloads fail safely.

An empty bounded scan records its continuation without claiming a complete calendar. One step's
range-complete result describes the requested horizon at that observation; the persisted Boolean
alone is not proof of arbitrary calendar-range completeness. Date-only obligations retain dates and
no invented UTC midnight. Technical attribution cannot act as a performer, approval or point award.

This is not yet a running scheduler. Fair multi-rule continuation, global budgets and shutdown,
durable review/calendar attention, relative sources and native/standalone background composition
remain required. See [step evidence](evidence/recurrence-materialization.json).

## Bounded fair application runs

The [fair run](../backend/src/domus/application/fair_recurrence.py) selects at most 50 active rules
and shares their turns within a global limit of 1,000 processed nominal slots. Replayed and historical
slots consume that work budget. Empty-period scans consume a separate bounded period budget.
The default horizon is 60 local days; it never deletes past backlog. Rule snapshots used for that
horizon are rechecked before the step can write.

A small [frontier](../backend/src/domus/domain/recurrence_frontier.py) persists the last actually
admitted rule. Reserving all 50 unread rules at once can starve later ones if every run stops after
its first step. Admission therefore advances before provider work for each visited rule, while
unvisited rules retain their turn across restart. The removed-rule key remains a lexical continuation;
it grants no authority and proves neither task completion nor arbitrary calendar completeness.

Current task/progress/proof facts remain authoritative. Results distinguish created, replayed,
historically absent and unconfirmed work, with bounded safe rule-specific attention. A malformed
post-commit acknowledgement cannot turn existing tasks into an empty-state claim. Cancellation is
checked before atomic admission, including after a writer wait; an admitted effect completes or
rolls back. No subsequent step begins after the cancellation is observed.

These are application runs, without a production thread or new HTTP surface. Owned polling,
startup/shutdown wiring, relative lifecycle and durable calendar/review attention remain required.
See [fairness evidence](evidence/recurrence-fairness.json) and the
[migration boundary](tasks/migration.md).
## Owned fixed-run polling lifecycle

Both persistent compositions now bind the real fixed runner through
[recurrence composition](../backend/src/domus/composition/recurrence.py). Merely constructing an
application does not start it. ASGI lifespan starts one
[owned worker](../backend/src/domus/infrastructure/recurrence_worker.py), which attempts an immediate
bounded run and waits five seconds after each attempt. The thread and waiting primitives remain
in infrastructure; application/domain planning and command code remain independent of them.

Composition validates its installation/channel against the repository and selects its actual current
household. It never accepts a maintenance actor or scope from a request or a stored rule. An
unconfigured installation stays unconfigured; no-active-rule polls do not churn frontier/business
records. Technical materialization needs no human HA request and cannot perform or approve work.

Shutdown sets cancellation, waits for the admitted step to finish or roll back, and joins before
identity/storage disposal releases the actual installation lease. The ASGI wrapper preserves prior
lifespan state and closes the worker on startup/application failure. Ordinary failures retain a safe
process-local category and wait before retrying; scope denial stops the worker. These observations
do not establish durable attention or full calendar completeness. Preview without SQLite has no
worker. The [lifecycle evidence](evidence/recurrence-lifecycle.json) separates real composed tests,
host smoke execution and fresh hosted CPU image results from owner-HA deployment.

Relative execution, durable attention/calendar predicates, protected public interfaces, reviewed
schedule changes and the complete retained recurrence contract remain unfinished.

## Strict stored text and initial inspection contention

Stored recurrence text now has to equal its exact canonical JSON representation before typed
construction. Semantically equivalent whitespace, key reordering and escaped keys are rejected
for rules, progress, slots and selection frontiers. Independent reads and snapshot validation
share this boundary and retain the altered database bytes rather than repairing them. Existing
semantic corruption fixtures use canonical serialization so they continue to exercise their
original source/effect invariants independently of syntax rejection.

A real exclusive SQLite writer can also block initial database inspection. That condition now
remains bounded `storage_busy` and a 503 response; other inspection failures still refuse invalid
databases. Native and standalone HTTP tests use actual independent exclusive writers and verify
explicit read recovery without another business effect.

The observed hosted browser trace had a rejected busy POST, one successful setup and a subsequent
authorization read returning `500 internal_error`. It did not retain the internal exception stack.
The exclusive-lock tests independently reproduce the inspection misclassification; the historical
stack is not inferred as proven. The concurrency browser assertion explicitly refreshes status
after both original POST responses, then checks the retained rejection and deliberately replays
the exact original request under current authority. Refresh never resubmits a POST. See the
[review corrections evidence](evidence/recurrence-review-corrections.json) for original failures,
complete-source validation, current images and remaining acceptance limits.

## Completion-relative source and planning values

[Relative records](../backend/src/domus/domain/relative_recurrence.py) now distinguish an initial
obligation from a successor derived from an original task cycle. Their generation/cycle keys
exclude approval time, mutable record revision and generated task IDs. Record construction
validates facts; it cannot authorize maintenance or prove current source state. Historical source
values survive later closure. The future durable consumer must verify live references, original
receipts and its retained inbox/closure before committing an effect.

LocalInstant retains the actual UTC performed instant, realized wall time/offset and pinned source
identity independently of a future fold preference. Actual work in the second autumn appearance
remains there under a first-appearance household policy. The internal epoch-local basis can lie
in late1969 under a negative offset; user NominalTime continues to require1970 or later. One pure
TaskCycle completion snapshot helper now supplies existing lifecycle checks and relative sources
without rewriting performers, actual work time or original rules after verification/reopening.

The [read-only planner](../backend/src/domus/application/relative_recurrence.py) receives the
current cycle and produces ready, waiting-verification, closed-source or inactive-rule facts.
It derives local calendar days from performed_at and retains milliseconds for timed deadlines.
Date-only work stays a date, including a wholly missing local date, without fabricating an instant.
Invalid provider facts and range overflow remain explicit failures. Paused/retired rules and
ineligible source states require no provider I/O.

The shared PlannedSlot retains the existing PlannedFixedSlot source name and encoding; existing
fixed rule membership and materialization remain unchanged. The
[planning evidence](evidence/recurrence-relative-planning.json) includes real SQLite lifecycle
facts and preserved task/evidence counts, not a persisted successor. Relative storage, original
proof/recovery, durable cycle closure and invalidation, global mixed-rule fairness and production
integration remain required. This increment changes no SQLite layout or owner HA installation.

## Fixed cursor rank integrity

A correct binding and a plausible count are insufficient for a durable continuation. The
[shared pure membership logic](../backend/src/domus/domain/recurrence_membership.py) now checks
that period_index/offset describe the exact consumed nominal prefix. The bounded Gregorian-cycle
calculation retains interval phase, DTSTART truncation, omitted dates and genuinely empty periods.
A position beyond the first exhausted calendar period or an offset beyond its actual candidates
is invalid. Count/date exhaustion and date-only UNTIL consumption also retain their original bounds.

[Repository progress reads](../backend/src/domus/infrastructure/sqlite_recurrence.py) verify the
rule relationship as well as canonical row headers. Writes, materialization and checkpoint
inspection share it; malformed progress is refused without repairing bytes or generating work.
These relations prove cursor consistency, not original effect processing, caller authority or
calendar completeness. Instant-UNTIL resolution retains the existing pinned provider boundary.

The [cursor evidence](evidence/recurrence-cursor-integrity.json) includes a replay of the meaningful
negative tests against every byte-verified original059 module, real canonical-row corruption and
genuine sparse/end continuations. The original test fixture binding mismatch was corrected
explicitly. No historical source or fixture bytes, SQLite layout or owner installation changed.

## Original proof for UTC UNTIL continuation

UTC UNTIL requires resolved boundary facts beyond nominal rank. Progress retains the last included
slot at its exact consumed rank, with an instant at or before the inclusive cutoff. Closing a cursor
requires the first excluded resolved candidate at that cursor, a conservative exhausted-period bound
or natural calendar exhaustion. A bounded unclosed cursor after the last included slot remains valid
until the following step checks the end. No provider is called by domain records or inside a writer.

Each real fixed progress advance now retains a typed time-evidence core in its original slot or scan
receipt. The progress document references that exact scoped command and operation; a separate
revision-bound evidence header agrees with both. The repository checks current or retained historical
receipts before writes and on independent reads. Checkpoint validation uses the same checks. A safe
zero-work rewind clears its old evidence explicitly; a fabricated run cannot borrow that exemption.
Actual restore reconciliation preserves absent work without new task IDs, receipts or events.

This changes the unreleased schema8 layout and closed progress encoding. Released historical1..7
inputs remain supported. The genuine prior b2bcc69 schema8 layout is a strict refusal control;
keeping its matching application/database pair permits development rollback without relabeling it.
See [UTC boundary evidence](evidence/recurrence-until-integrity.json) for original-source replay,
logical-dump correction, current verification and remaining full-feature acceptance.

## Original generation facts in historical slots

An older slot may remain valid after the current rule changes. That relationship cannot prove
which pattern produced it: another pattern can admit the same nominal date and leave its key
unchanged. The slot now checks its original receipt's pattern-and-policy cursor binding, explicit
policy, complete planned/resolved facts and scoped resource identifiers. Canonical JSON comparison
keeps boolean/integer aliases distinct. Current and retained-current originals remain valid;
historical absent-effect proofs cannot claim a present slot.

Point/page repository reads and checkpoint inspection share this pure check. Malformed originals
receive a safe record failure without changing source bytes. Snapshot validation no longer uses a
weaker duplicate identifier-only check. Actual earlier-generation positive controls and an unchanged
genuine06 source database verify compatibility. Synthetic repository fixtures now carry explicitly
complete synthetic source proof; they do not establish actual materializer acceptance.

See [original slot evidence](evidence/recurrence-slot-original.json). This refinement changes no
layout, dependency, timezone I/O, timeout, owner installation or retained original operation.

## Shared rule identity and relative persistence

Fixed and completion-relative rules now share globally unique rule/progress rows with an explicit
timing kind. Deferred generation relationships and compare-and-swap predicates include that kind.
One nonretired rule owns a definition's current timing; retired history remains. This preserves
the definition-based selection budget and prevents a typed writer from overwriting the other kind.
Shared row mechanics stay in infrastructure, behind the existing semantic recurrence port.

Relative progress binds the complete immutable generation, including initial due fact, interval,
visibility and policy. Even an unconsumed cursor cannot silently accept different valid timing.
Every actual progress claim also requires an original scoped command/operation whose canonical
result matches the business continuation. Its revision-bound proof header covers the stored record.
CAS revision and observed last-run time are separate from business cursor identity. Unknown versions,
fields, alternate canonical text and boolean/integer aliases are refused.

A relative slot preserves complete original generation, planned/resolved and normalized source facts
in its evidence fingerprint. Reads verify its actual task and source-cycle relationship, including
the original completion after later approval or closure. That is retained factual history; it does
not establish source eligibility or perform successor invalidation. Constructors and saved records
grant no maintenance capability. Corrupt originals on reads or writes are storage failures.

Actual offline restore tests keep a generated successor absent when its original task and mapping
were rolled away. They separately preserve an adopted manual task that still exists while its later
mapping is absent. Both keep original proof without new task IDs, receipts or event delivery. A
historical pointer cannot authorize automatic recreation of that processed mapping.

The schema8 layout is unreleased. Supported released1..7 fixtures remain unchanged; the genuine
[prior06 layout](../tests/fixtures/sqlite/unreleased-06b3b9f-schema8.sql) is refused unchanged rather
than relabeled or silently upgraded. No owner HA installation changes. See
[relative storage evidence](evidence/recurrence-relative-storage.json) for exact measured scope.

Actual relative initial/successor materialization, reviewed attachment, source inbox/closure and
eligibility, restore-source reconciliation, successor invalidation, mixed-rule execution and runtime
wiring remain required. Synthetic repository receipts and image codec/storage controls do not
establish those consumer journeys or the remaining calendar/UI/HA/all-domain release acceptance.

## Authorized relative creation

RelativeRecurrenceCommands now accepts a typed explicit initial local date or time, interval,
time policy and successor visibility. Its immutable request fingerprints those facts with the
validated task content, overrides and material selections. Existing creation/configuration/material
grants apply. Current HA proof and local authority precede original lookup; local grants are checked
again inside the writer after external timezone preparation. A caller cannot supply a resolved
initial deadline in place of the pinned semantic time port.

The atomic operation saves one task definition, one active relative rule and pristine generation-bound
progress together with the original receipt, audit and outbox. It leaves the first obligation
unconsumed for actual materialization; ordinary title-only manual creation keeps its existing behavior.
The initial gap moves to the first valid local instant and folds retain one configured appearance.
Date-only obligations retain their local date without becoming midnight instants.

Tests include independent simultaneous SQLite writers, failure after every write, restart replay,
provider/grant races, material ownership and real offline restoration of the whole creation. A
historically processed creation returns original evidence without recreating its restored-away
definition/rule or event delivery. This is distinct from the still-required relative materializer,
source inbox/closure/eligibility/invalidation, reviewed attachment and mixed-rule runtime. See
[relative creation evidence](evidence/recurrence-relative-creation.json) for measured scope and limits.


## Cycle-closure policy before durable integration

The pure RelativeClosure policy records one original consumer grant or terminal fence per source
cycle. Its identity spans rule generations and later approval/reopening while preserving the exact
installation, channel, household, rule, definition and source occurrence/cycle. Original successor
and completion snapshots remain immutable. This consumer proof does not close or approve the human
TaskCycle, authorize maintenance or create an obligation by construction.

A later rejection or reopening may cancel only derived work proven never to have started. Existing
cancelled/skipped work is retained; started/completed work or unknown history requires review.
Retained processing proof cannot recreate an absent successor. Closure chronology includes rule
creation and the observed human decision; zero is a valid timestamp.

The 61 pure-policy tests and full backend campaign are recorded in
[lifecycle evidence](evidence/recurrence-lifecycle-calendar.json). Durable inbox/closure storage,
atomic source revalidation and successor effects, schema-10 compatibility, mixed execution and
calendar/UI integration remain required. The current runtime runner does not yet consume this policy.
