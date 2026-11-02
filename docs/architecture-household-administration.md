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
below; the separate administration journal and the full EN/ES workspace remain required.

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
browser tests; the administration controller, journal and workspace integration remain outstanding.

[Composition](../backend/src/domus/composition/household_administration.py) binds the same
transactions and trusted human adapters as the existing household services. Preview factories
without the administration callback do not register or advertise those routes. Capability metadata
describes wired routes and the closed journal contract; it grants no permission and does not
establish that the future browser workspace/journal is implemented.

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
