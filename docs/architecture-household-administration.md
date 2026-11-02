# Household administration architecture

The first source checkpoint adds immutable public presentation and private preference records in
[member profiles](../backend/src/domus/domain/member_profiles.py). These pure values contain a
household/member reference and their own positive revision. They contain no HA account, role or
status and cannot authenticate or authorize a request. Alias edits and private preference changes
have separate state and revisions; a public presentation record never includes preference values.

An alias is null or trimmed text of 1–80 Unicode code points. UTF-8 and every Unicode Cc control
are checked before whitespace normalization. Literal markup stays literal data; the eventual
renderer must display it inertly. Null explicitly clears the alias. A missing alias does not invent
an HA display name or avatar. The source adapter supplies actual verified name facts or an explicit
unavailable result, independently of human proof. Avatar delivery is unavailable.

Private preference values are browser-following/null, English or Spanish locale, plus a strict
routine-summary boolean with true as the engineering default. Persisting a preference does not
establish notification delivery. The current application, metadata and HTTP behavior is described
below; browser lifecycle integration and the full EN/ES workspace remain required.

The [companion](../specs/household-administration.md) retains all 24 Action-published case rows and
adds the omitted independent risks to a 72-case floor. Its original identity and delivery owners
remain unchanged. The pure checkpoint runs on the admitted schema-7 base without changing storage
or APIs; persistence integration follows recurrence's actual schema-8 merge before schema 9.

The subsequent issue21 integration adds schema9 after the real PR22 schema8 merge. Application
[profile ports](../backend/src/domus/application/member_profile_ports.py) expose independently
revisioned public presentation and private preference repositories. The
[SQLite adapter](../backend/src/domus/infrastructure/sqlite_member_profiles.py) decodes persisted
records strictly and compares canonical member/household scope and expected revision on updates.
New member creation persists both domain defaults atomically; membership updates leave those
records untouched. No preference values enter public identity records, audit or outbox through
these storage operations.

## Current application and protected HTTP

[Profile commands](../backend/src/domus/application/member_profile_commands.py) use fresh human
proof outside SQLite, then reread current local grants in the atomic writer. The caller derives
from the established session; preferences have no member or household selector. An alias edit
requires current member-management permission or the owner's applicable preference permission.
It does not activate a pending member or change their private preferences or membership revision.

[Profile queries](../backend/src/domus/application/household_administration_queries.py) require
current member-read authority for public aliases and current owner-scoped preference-read authority
for preferences. A missing private record is a storage failure, not permission to initialize one.
The [original-result guard](../backend/src/domus/application/member_profile_access.py) runs before
returning profile receipts. Another administrator cannot obtain an owner's original private result
by knowing its request key or operation ID. Revoking the original action permission blocks its
replay and disclosure even if ordinary preference reads remain permitted.

Effects, immutable results and safe audit/outbox facts commit together. Shared facts include scoped
member/revision/transition evidence, with no private preference values or inferable request/result
fingerprints. Independent writers use the actual database compare-and-swap behavior. Restoration
retains the original result and its historical absent-effect warning without recreating an effect.
Technical outbox acknowledgement is recorded separately from unavailable notification delivery.

The [HTTP adapter](../backend/src/domus/entrypoints/administration_http.py) reuses the established
body, session, Origin, CSRF and context boundaries in both deployments. Closed DTOs reject owner
injection, ambiguous revisions and unknown fields. A read-only original-request lookup admits only
the five administration actions, derives the actor from the current session and never resends a
mutation. Existing operation-ID lookup uses the same original-result guard. Neither GET requires a
mutation CSRF token or expected revision. Revisions remain exact JSON integers through int64;
browser consumption must preserve their lexical value rather than rounding through Number.

The [shared OpenAPI projection](../backend/src/domus/entrypoints/openapi.py) restores the exact
maximum of explicitly declared int64 fields after FastAPI projects numeric bounds through float.
Smaller bounds, unmarked integers and approximate number fields remain untouched. The original
framework and actual composed API controls distinguish that schema issue from request validation.

Browser [administration values](../frontend/src/domain/administration.ts) use canonical decimal
revision text and bounded BigInt arithmetic. The [JSON codec](../frontend/src/adapters/administration-json.ts)
validates duplicate decoded keys, depth, bytes and integer lexemes, then obtains each numeric
value's original source. A numeric string or lookalike object cannot become a wire integer, and an
engine without original-source support fails closed. Fixed profile encoders publish an exact
integer lexeme with only the supported payload fields. These pure values/transport helpers have
browser tests and application-controller consumption; browser workspace integration remains outstanding.

[Composition](../backend/src/domus/composition/household_administration.py) binds the same
transactions and trusted human adapters as the existing household services. Preview factories
without the administration callback do not register or advertise those routes. Capability metadata
describes wired routes and the closed journal contract; it grants no permission and does not
establish that the browser workspace or journal integration is implemented.

The [migration guide](household-administration-migration.md) identifies genuine immutable source8
input, historical migration behavior, independent checkpoint validation, image checks and compatible
rollback. This storage increment does not reduce or complete the retained 72-case product scope.

The [checkpoint evidence](evidence/household-administration.json) distinguishes the initial failing
test, complete backend execution, per-module/global coverage, independent audit and architecture
contracts. No packaged update or owner-HA administration journey is claimed by this checkpoint.

## Bounded source facts and current roster

[Source values](../backend/src/domus/domain/member_sources.py) distinguish a complete directory,
confirmed omission, denied access and unavailability. Names are nullable, literal valid UTF-8 of at
most 256 code points, with no Cc controls or whitespace-only labels. An eligibility fact is a strict
boolean and never supplies a household role or grant. The complete source bound is 256 unique
accounts, including ineligible records; overflow/malformed data is not truncated into success.

The [HA adapter](../backend/src/domus/infrastructure/ha_member_profiles.py) uses the existing fixed,
bounded WebSocket transport. HA2026.10.4 exposes account names through
[own-user source](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/auth/__init__.py#L513)
and the administrator-only
[directory source](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/config/auth.py#L19).
Neither response supplies an account avatar. The adapter makes at most two metadata requests: a
complete directory read and, if it fails, an optional exact-own OAuth read. Native technical grants
never use that fallback as the human. Protocol facts, fake-provider execution and owner HA evidence
remain separate; no live owner directory acceptance is claimed here.

The standalone identity adapter reuses one private credential gate for directory and metadata
operations. Current read proof permits only the original bounded outage lease; authorizing directory
proofs for mutations still require fresh write proof. Refreshed tokens retain the original deadline.
Logout, expiry or credential replacement before/during a lookup discards its result. No token enters
the application port or HTTP response.

[Roster queries](../backend/src/domus/application/household_roster.py) require current authority
before source access, release SQLite before provider I/O, then recheck human identity and local
authority before disclosure. A changed membership/policy snapshot requires a fresh view. Alias
updates use their independent current revision. Existing linkage/exception masking is reused;
metadata is declassified to state and name before leaving the application, without HA IDs or
eligibility. Unknown names stay unavailable while canonical local membership remains. Directory
choices require policy management and contain only complete, source-eligible facts. No query
initializes household, membership, profile or preference records.

## Separate bounded browser recovery

The [closed command policy](../frontend/src/domain/administration-commands.ts) admits only
`household.update`, `member.update`, `policy.update`, `member.presentation.update` and
`member.preferences.update`. Each payload contains a canonical decimal-text revision. Member
targets occur only on the two member-targeted actions; private preferences have no owner selector.
Ordinary permission decisions are bounded, unique and exclude protected grants. Mapping mode and
target agree. Validation copies and freezes nested values without replacing original text, ordering
or revision intent. Timezone catalog and current authorization remain server responsibilities.

The pure [administration journal](../frontend/src/domain/administration-journal.ts) owns namespace
`administration`, version 1, at most eight requests in total and a one-hour immutable lifetime.
Each record retains its original installation, release channel, verified subject, action, target,
key, payload, creation/expiry and outcome. Switching contexts hides other contexts' requests while
retaining their unexpired originals. All contexts share the eight-record and total byte budgets;
switching accounts cannot evade the bound. A known operation ID cannot change or become unknown.
Prepared/uncertain records cannot be dismissed as resolved, and expiry never extends their deadline.
The journal neither authenticates a context nor grants backend original-result disclosure.

An [application port](../frontend/src/application/administration-ports.ts) exposes only the current
context view. Its [session-storage adapter](../frontend/src/adapters/administration-journal.ts) uses
only `domus.administration.journal.v1`, separate from the unchanged entry journal. Canonical JSON
and the 65,536-byte UTF-8 limit are checked before decoding and persistence. Duplicate/noncanonical
encodings, unknown fields, wrong namespaces and numeric revisions fail closed. Compare/readback
fences reject competing or unconfirmed storage writes and retire the in-memory handle. Detach
does not erase pending requests; forgetting a resolved request leaves other contexts and all
unrelated storage intact. Credentials, CSRF, cookies, raw HA facts and response bodies are absent.

Chromium tests exercise these policies, real isolated browser session storage and provider failure
controls. The application controller consumes the journal through its semantic port. The browser
composition and complete workspace do not yet connect that controller. These tests establish no
automatic operation lookup, mutation replay, HA adoption or full retained-case acceptance.

The workspace companion now decomposes its eight requirements into 82 prospective acceptance
scenarios with explicit per-area risk budgets and reciprocal requirement links. Its former eight
compound scenario IDs remain as concrete behaviors; the remaining assertions have their own IDs.
The original 80 workspace rows remain, with two independent scope-binding/recovery cases added.
The original 72 administration cases and eight HADI refinements remain unchanged and required.
These inventories are not added together as completed journeys, and 104 journal-related test
executions do not establish the full browser, runtime, migration or manual-review acceptance.

## Exact HTTP clients and entry compatibility

The [shared JSON/scalar boundary](../frontend/src/adapters/json-values.ts) validates syntax,
decoded-key uniqueness, depth, original integer lexemes and UTF-8 byte bounds before projecting
facts. Positive aggregate revisions use canonical decimal text throughout browser models; the
unchanged entry setup/enrollment payload keeps its initial literal zero. Timestamps and small
protocol counters require exact safe integers. Entry membership/policy checks, household reads
and original enrollment policy revisions use the same exact representation. Valid backend Unicode
household text is not reinterpreted through JavaScript's different trimming policy.

The [bounded HTTP transport](../frontend/src/adapters/http-transport.ts) keeps the verified
same-origin application base, context assertions, no-store/content-type checks, redirect refusal,
fatal streaming UTF-8 decoding, cancellation and the existing deadline. Standard responses retain
the 65,536-byte bound. Complete roster/directory reads have a separate 1,048,576-byte bound; tests
exercise 256 members with maximal UTF-8 names/aliases and every supported ordinary permission.
Oversized replies fail without publishing partial rosters. The browser journal limit remains
65,536 bytes in total and is not used as a limit for a complete server roster.

The [administration client](../frontend/src/adapters/administration-http.ts) exposes only fixed
supported reads and five explicit mutations. Strict projections preserve masked linkage and source
states, separate stored/effective roles, validate response targets and retain exact revisions.
Fresh CSRF precedes each PUT. The original key, payload and expected revision are never rebased or
replaced. Known rejection envelopes expose safe reason/correlation only; lost, malformed or unbound
mutation responses remain uncertain without an automatic resend.

Protected GET recovery by action/key and by an already captured operation ID keeps its existing
contract, without mutation CSRF or revision parameters. The key route binds returned action/key;
the ID route binds its captured operation ID. Both validate the original action-specific result
and successor revision before returning it. These are processing receipts, not current aggregate
facts; technical event delivery never establishes notification delivery. Non-profile lookup text
retains its original domain label rather than being renamed as a profile change.

Browser lifecycle consumption, complete EN/ES forms and full administration browser acceptance
remain required. Entry browser compatibility uses
actual Python/SQLite in both deployment fixtures; fixture identities and directly seeded high
revisions do not claim owner HA adoption or a generated history of that many mutations.

Current wheel and source-image acceptance compare every packaged UI resource with the explicit
`currentSourcePackage` inventory in the administration evidence. The wheel gate first compares
that declaration with the actual local build; the image gate independently compares it with the
installed image and served bytes. Historical entry delivery and installed Edge.5 evidence retain
their original source, resource hashes and adoption claims. A new source build does not inherit
those historical package identities.

## Administration application controller

The [controller](../frontend/src/application/administration-controller.ts) uses semantic session,
server, journal, clock and entropy ports. It has no concrete HTTP/storage, framework or DOM import.
The [pure availability policy](../frontend/src/domain/administration-authorization.ts) consumes
current active membership and decoded grants. Stored/effective role labels and provider facts do
not grant an action; the backend independently reauthorizes every operation.

Refresh reads a verified session, current access and version-2 capabilities, then collects only permitted
facts. Failed reads stay unavailable with a scoped safe reason. Owner preferences must name the
current authorization member. The server-owned household routing identifier in capabilities binds
household/policy facts and receipts independently of current aggregate-read permission. The
identifier does not claim household existence, select a caller or grant access. Legacy unbound
version-1 capabilities and unknown versions fail closed; journal version 1 remains unchanged.
Access is read again after collection; changed grants or membership
discard the collected private view. Replacing the same account's membership also retires any old
private receipt. Read-only outage leases allow permitted local facts until expiry, without enabling
a mutation. Existing owned-journal GET recovery remains available under the same read lease.

An explicit submission refreshes proof and facts, checks the captured exact aggregate revision,
rejects exhaustion, and persists the original command before one send. An unresolved request blocks
replacement work on the same aggregate while different explicit aggregates remain possible within
the global journal bounds. A known rejection stays rejected; an unbound or lost mutation reply
stays uncertain. No submission is rebased or retried automatically.

Explicit recovery refreshes proof and original-action authority, checks the unchanged stored
original, and performs only the protected key GET or captured-ID GET. It never calls the mutation
port or adds a current aggregate-read/revision precondition to that existing lookup contract.
Processing receipts and current facts remain separate, including historical results after restore.
A journal failure after a valid result preserves that result in memory on its verified context;
it does not turn a saved effect into a failed mutation or erase the stored original.

Generations fence canceled reads, preflight, commands and lookup responses. Closing or expiring the
controller hides private facts immediately; late results cannot repopulate them. Journal views hide
currently unauthorized action payloads while retaining underlying unexpired originals. Explicit
dismissal removes only a resolved owned request. Composition still needs to wire the controller to
page lifetime and the complete localized forms; controller/port tests are not those product journeys.

Valid read-only outage leases also retain the existing local original-result GET contract, including
explicit journal recovery. Both actual deployments return the owned original without changing
database bytes. The controller permits that lookup and local resolved-record dismissal until the
unchanged session deadline, while new submissions remain blocked. Recovering a receipt neither
renews the lease nor replays the mutation.
