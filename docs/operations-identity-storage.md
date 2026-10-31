# Identity and storage operations

Status: standalone authentication API/CLI, transactional SQLite core and schema 2 are implemented.
Application-layer household/member/policy commands and standalone public routes are implemented.
Console recovery approval, snapshot/restore commands, persistent Supervisor runtime wiring and
complete deployment acceptance remain pending. Do not use SQL edits to bypass setup.

## Authentication API

| Route | Purpose | Required boundary |
|---|---|---|
| GET /api/v1/auth/start | Create one browser-bound attempt and continue to fixed HA authorization | Strict empty query, valid configured host |
| GET /api/v1/auth/callback | Consume matching attempt, exchange/prove and issue rotated session | Exactly one code or decline result, state, private browser cookie |
| GET /api/v1/session | Current own verified identity and full/read_only state | Opaque server cookie and current proof/bounded grace |
| GET /api/v1/auth/csrf | Obtain a nonce for that own session | Same session boundary; no credentials in the response |
| POST /api/v1/auth/logout | Clear local access and attempt only its own grant revocation | Exact Origin, session-bound X-CSRF-Token and strict empty JSON object |
| GET /api/v1/openapi.json | Inspect actual versioned schemas and declared cookie/error contracts | Configured host; no private records |

All API responses disable caching and referrer forwarding. Errors use a stable code, state, impact,
next action and server-created correlation; input/provider details are not reflected. Framework
validation cannot echo an authorization code. Unknown paths and methods do not redirect. There is no
HTTP recovery-approval route. The standalone [household/member/policy/operation routes](household-api.md)
are enabled by --database; recovery routes remain pending.

## Retained state and recovery

| Event | Retained / removed | Operator action |
|---|---|---|
| HA temporarily unavailable | Existing bounded session may query; writes denied | Reconnect; never extend lease or invent proof |
| HA explicitly rejects identity | Local lease and credential removed immediately | New eligible sign-in; no outage fallback |
| Login code exchange/proof fails | Attempt consumed, no browser session issued; owned received grants get bounded cleanup | Start a deliberate new attempt; inspect HA authorization if cleanup is unconfirmed |
| Local sign-out / response loss | Local access is removed; upstream result may be true, false or null/unknown | Retrying local sign-out is safe; never infer remote success from absent private material |
| Process stop / restart | Every local credential/lease disappears; business SQLite remains separate | Reauthenticate; review reported unconfirmed HA grants as needed |
| Schema/identity/channel mismatch | Existing database is not adopted or rewritten | Use the matching installation/image; follow the migration guide |

Normal sign-out attempts the exact delegated grant. Expiry/known rejection erases local material and
does not promise HA-side revocation. Shutdown clears all local leases first and attempts at most two
bounded remote revocations. Its counters describe owned records handled during that shutdown, not
an enumeration of every authorization retained by HA. A failed or unknown remote cleanup never
restores Domus access; HA profile authorization management remains available to the account owner.

The CLI disables access/query logging. With normal info logging enabled, auth_runtime_stopped reports
only revoked/unconfirmed counts. No token, browser nonce, actor name or callback code appears there.
Controlled live tests must identify source/channel/versions, obtain the required HA consent and
record cleanup without retaining credentials or unnecessary personal data.

## Durable data and future operator commands

SQLite commits household state, policy, scoped receipts, audit and outbox atomically. Outbox delivery
failure does not reverse a committed business result. Retain replay evidence across restart, migration,
cleanup and future restore. [Schema 1-to-2 migration](migrations-identity-storage.md) is additive and
atomic; old households without policy fail closed rather than promoting a browser.

Console-approved administrator recovery must still require a fresh current HA administrator, exact
target/request/UUID/channel/mapping binding, ten-minute expiry and atomic single use. Snapshot/restore
must still verify consistent schema/identity/integrity/checksum and activate only a new owned directory.
These commands are not yet present. No automatic backup frequency or retention has been approved.

The [native persistent runtime](native-household-api.md) clears only its local bindings on shutdown;
Supervisor owns its upstream cookie and transport grant. Reopening through HA freshly proves the
human, while the matching SQLite records and receipts survive. Its fixed-origin configuration and
original lease deadline apply independently of forwarding headers. This runtime is not yet the
installed Edge app; private-directory provisioning and updated live acceptance remain pending.

The [owned data lifecycle](owned-data-directory.md) now persists UUID/channel initialization state
and holds a process lock for the native listener. A ready installation refuses missing/empty SQLite
instead of recreating it. Interrupted first initialization resumes only the stored UUID. Metadata,
database and replay records must remain together; deleting identity metadata is not a recovery step.

See [configuration](configuration.md), [user identity journey](identity-household.md),
[implementation boundaries](architecture-identity-storage.md), [the M1 companion](../specs/platform-foundation-identity-sqlite.md)
and [compatibility gates](compatibility-home-assistant.md).
