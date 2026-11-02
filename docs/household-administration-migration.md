# Member profile storage migration

Issue [#21](https://github.com/vypdev/domus/issues/21) adds schema9 on the actual schema8
checkpoint merged in [PR #22](https://github.com/vypdev/domus/pull/22). The
[integration companion](../specs/household-administration-integration.md) retains the complete
[administration contract](../specs/household-administration.md). Storage is one implementation
increment; it does not establish the workspace, owner-authorized HTTP commands, HA presentation
metadata, notification delivery, or any of the 72 complete administration journeys.

## State and defaults

`member_presentations` holds the canonical member/household references, nullable public alias,
and its own revision. `member_preferences` holds those references, nullable locale, the strict
routine-summary flag, and a separate revision. Both reference the existing composite member
scope. Existing identity, membership status, permissions and HA links remain authoritative.

Migration creates one explicit record of each kind for every existing member, including pending,
suspended and archived members. New member creation initializes both domain-defined defaults in
the same transaction. Defaults are alias null, locale null (browser-following), routine summaries
true, and revision1. A default does not invent an HA name or deliver a notification. Membership
updates preserve profile state; alias and preference revisions do not invalidate one another.

Storage ports do not authorize a caller. The eventual application commands and queries must
enforce current source/local authority, owner-only preference disclosure, CSRF/context, immutable
original requests, and safe audit/event content before exposing this state. Direct repository
tests are not acceptance of those boundaries.

## Genuine upgrade inputs

Supported initialization inputs are the original schema1 through schema8 fixtures. Historical SQL
files remain unchanged. The new [schema8 fixture](../tests/fixtures/sqlite/v8.sql) is a byte copy
of the complete logical dump captured from published source
`ed7cd14190d750846833cf1bb822988b628560da`, including the original `application_id` and
`user_version` pragmas. It was not reconstructed by current code or relabeled as an older schema.

| Original input | SHA256 |
|---|---|
| Private raw source database | `badd63184fa40380462ab3fe54cd957b63a967d1beafb4b73fc6c2475df8340b` |
| Complete logical dump / committed v8 fixture | `041615f0253c0537ac6c713e10a8984fb5043b1f6df29a6a2c7193824ebc6ed5` |
| Published source archive used by compatibility image | `1d5c69cd2a61f2e8b2c7702ea112a2034c7849f4f59d3a479e41be001b8f2454` |

The source fixture has its own original installation UUID
`00000000-0000-0000-0000-000000000007` and Edge channel. Compatibility tests read that identity
instead of modifying it to match another fixture. Its fixed slots, pristine relative progress,
task state and six original operation/audit/outbox records are real application output with
fictional HA proof. They contain no owner HA data and do not prove relative materialization.

Ordinary reads/writes refuse previous schemas. Explicit initialization verifies installation and
table ownership, then performs historical additions and schema9 additions inside one transaction.
Only successful completion writes version9. Source8 task, recurrence, identity and operation rows
remain identical. Earlier supported migrations retain their existing transformations: schema5
task documents acquire schema6 empty material snapshots and version2; original receipts, cycles,
audit and events remain unchanged. No schema1..8 input is edited to achieve compatibility.

## Failure, restoration and rollback

An invalid addition or a late write failure rolls back the new records, tables and version together.
Tests compare the original database bytes after injected migration failure for each supported
input. A changed version number without the two profile tables cannot authorize profile use.
Missing or invalid persisted profile records fail closed; reads do not silently recreate defaults.
Checkpoint inspection independently checks schema, foreign keys and both profile records for
every member, in addition to existing task, recurrence and operation integrity checks.

Existing offline checkpoint preparation, installation leases, generation selection and restoration
continue to apply. A current checkpoint includes public aliases and private preferences. Restoring
that checkpoint restores its profile state, while the prior complete source remains available
under the existing rollback contract. Original processed-operation evidence is retained separately;
restoration cannot replay an old effect as new work.

A previous application must refuse schema9 and selected newer generations without changing files.
Compatible rollback requires the matching complete application, database and installation/generation
state; running an old executable against the schema9 database is not a downgrade procedure. The
[immutable schema8 image](../tests/fixtures/schema8-app/Dockerfile) builds the complete published
backend and frontend from its checksum-pinned archive. Every PR CI Check runs it with both current
CPU images for real upgrade, snapshot inspection, refusal and restore controls. Hosted results must
pass before image compatibility is claimed. Host execution of a packaged test script establishes
only host behavior.

The installed owner Edge.5/schema7 package is unchanged. This increment does not publish a release,
promote Stable/Edge images, update HA, or accept the remaining recurrence/calendar issue
[#23](https://github.com/vypdev/domus/issues/23).
