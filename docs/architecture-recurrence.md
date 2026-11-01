# Recurrence temporal foundation

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

Rule parsing/expansion, task classification, schema 8, durable materialization, source consumption,
preview/apply, calendar queries, the composed runner and actual image/browser/HA acceptance remain
outstanding. All 52 companion cases and 37 original owning cases remain requirements. This
checkpoint does not establish those journeys, a shipped package, Stable distribution or the first
all-domain release.

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
