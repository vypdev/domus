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

The [migration guide](tasks/migration.md) distinguishes current source schema 8 from the immutable
installed Edge.5 schema 7. CI builds a separate checked-out-source image for both CPU architectures
and retains Edge.5 as a genuine old-image compatibility control. Its version is ci-current and it
has no publication/deployment step. Actual hosted build/test outcomes remain required evidence.

These are repository and migration capabilities. Scheduled human commands, actual fixed/relative
materialization, lifecycle consumption, restore non-recreation, preview/apply, protected calendar
queries and composed runners remain unfinished. The four additional storage refinements do not
recount the retained 52 companion or 37 original owner cases. See
[storage evidence](evidence/recurrence-storage.json) for exact tests and acceptance limits.
