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
