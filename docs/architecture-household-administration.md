# Household administration architecture

The first source checkpoint adds immutable public presentation and private preference records in
[member profiles](../backend/src/domus/domain/member_profiles.py). These pure values contain a
household/member reference and their own positive revision. They contain no HA account, role or
status and cannot authenticate or authorize a request. Alias edits and private preference changes
have separate state and revisions; a public presentation record never includes preference values.

An alias is null or trimmed text of 1–80 Unicode code points. UTF-8 and every Unicode Cc control
are checked before whitespace normalization. Literal markup stays literal data; the eventual
renderer must display it inertly. Null explicitly clears the alias. A missing alias does not invent
an HA display name or avatar. The future profile adapter must supply actual verified presentation
facts or an explicit unavailable result, independently of human proof.

Private preference values are browser-following/null, English or Spanish locale, plus a strict
routine-summary boolean with true as the engineering default. Persisting a preference will not
establish notification delivery. Current owner-only query/command authorization, provider metadata,
HTTP contracts, the separate administration journal and the actual EN/ES workspace remain
to implement. These records do not establish their acceptance.

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
these storage operations. Application authorization and original-result privacy remain required
before these repositories gain any HTTP or workspace consumer.

The [migration guide](household-administration-migration.md) identifies genuine immutable source8
input, historical migration behavior, independent checkpoint validation, image checks and compatible
rollback. This storage increment does not reduce or complete the retained 72-case product scope.

The [checkpoint evidence](evidence/household-administration.json) distinguishes the initial failing
test, complete backend execution, per-module/global coverage, independent audit and architecture
contracts. No packaged update or owner-HA administration journey is claimed by this checkpoint.
