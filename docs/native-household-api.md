# Native Home Assistant household API

Status: persistent native runtime, local session leases and common household routes are implemented
and tested with real ASGI/SQLite composition. Edge 0.0.0-edge.2 now packages this runtime and passes
owner update/configuration/start, existing-session access, normal reload and restart. The product UI
is still a connection page. Live household/recovery commands are not inferred from that acceptance.
Automatic identity and private data use the [owned lifecycle](owned-data-directory.md).

The installed Edge.2 pin remains on schema 3. The new schema-4 runtime tests additionally exercise
historical replay, suppressed delivery and recovery closure through this same native composition.
That new code is not yet packaged or installed; offline restoration is tested locally and full acceptance
remain pending. See [history boundaries](restoration.md).

## Authentication and session binding

Open Domus through its HA app page. Supervisor authenticates the existing Ingress session and strips
client-supplied human identity headers before setting the associated user. Domus accepts protected
requests only from the actual Supervisor socket peer with proxy rewriting disabled, a valid Ingress
base path, one exact subject and one valid existing `ingress_session` cookie.

Domus never sets another browser cookie or starts another OAuth sign-in. A keyed hash binds the
upstream session to installation UUID, channel, subject and app path. Only that digest and bounded
local lease records are retained in process memory; the HA cookie is never stored in business SQLite,
logs, audit, outbox or evidence. Request metadata is not human proof: creating a local lease and every
write require a fresh exact active non-system human lookup through the private Core transport.
Its technical administrator privilege never becomes the person's Domus role.

The default local lease has a one-hour absolute deadline; the shared policy permits five minutes to
eight hours. Fresh reads do not extend it. A bounded HA availability failure permits only local reads
until that original deadline, under current local membership/policy. Writes fail. Explicit rejection
or identity mismatch removes the lease; a later outage cannot revive it. An expired lease needs fresh
HA proof before a new safe read can create a new lease. Writes and supplied CSRF never bootstrap one.
A new lease has a new CSRF epoch. Shutdown clears local bindings and blocks late authentication.
Supervisor owns the upstream cookie and transport credential lifecycle; Domus does not revoke them.
No instant global HA-logout or cross-application session-revocation claim is made.

## Fixed origins and CSRF

The operator supplies one to four exact public HA origins, including internal/external origins as
needed. Values are validated and duplicates rejected before SQLite initialization. Request hosts,
forwarding headers, names and display labels cannot select the HA destination, accepted origins,
requesting user or administrator source. The Core destination remains the fixed Supervisor proxy.

GET `/api/v1/auth/csrf` verifies the existing native session or freshly establishes one through HA.
It returns a process-private-key MAC scoped to that exact binding and local lease epoch. Every write
requires one X-CSRF-Token and one exact allowed Origin, plus the shared Idempotency-Key/revision
contract. Copying a token to another cookie, subject, path, installation or channel cannot grant access.
No cross-origin CORS permission is emitted. Origin validation alone is not authentication.

## API and data

GET `/api/v1/session` reports the exact human, source, full/read_only access and remaining lifetime.
GET `/api/v1/openapi.json` exposes the [actual native schema](contracts/native-household-api.openapi.json)
through the same native boundary. The [household routes](household-api.md) share the same DTOs,
application use cases, privacy filtering, revision checks, last-administrator safeguards and atomic
receipt/audit/outbox semantics as standalone. Unknown input and ambiguous JSON remain rejected.
Unexpected response failure after commit preserves uncertainty and same-key recovery.

A selected ordinary HA human can manage Domus through the configured mapping. The native directory
uses private Core transport to verify other people without granting the actor HA administrator
status. Current Domus permission is still checked in the transaction. Source changes and local
suspension apply to existing leases and old privileged receipts.

The CLI development contract is:

```sh
domus-ingress --channel edge \
  --database /owned/app-data/domus.sqlite3 \
  --instance-id 047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6 \
  --public-origin http://homeassistant.local:8123
```

The UUID is the public fixture, not an identifier to reuse across real installations. The parent
must exist and be writable by the runtime. The operator preserves the actual installation UUID and
channel across restarts. Repeat --public-origin for additional configured HA origins. Partial option
sets are rejected. Omitting all persistence options retains the original connection preview.
SUPERVISOR_TOKEN is provisioned privately by HA and must never be copied into a command or document.

This listener is exclusively for the Supervisor private container network, binds no public app port
in the reviewed manifest and disables proxy-header rewriting/access logs. GET /health is nonpersonal
process readiness for Supervisor/loopback, not an HA availability or authenticated-user claim.
Packaged ownership/startup and both native CPU-family image checks pass. The complete UI, live
household/recovery operations and restore remain pending. Packaged snapshot create/inspect commands
also pass with the image's SQLite 3.46.1 in isolated fixtures, without creating an owner Domus snapshot.

[Administrator recovery](administrator-recovery.md) now shares this boundary and the standalone
application services. Human request/status/completion/cancellation are authenticated routes; approval
is available exclusively from the installation console. Schema 3 migration and local fixtures do not
establish live recovery acceptance in the installed package.

## Reviewed primary sources

- [Core 2026.10.4 Ingress proxy](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/hassio/ingress.py): generated base path and forwarding behavior.
- [Supervisor 2026.10.5 Ingress](https://github.com/home-assistant/supervisor/blob/2026.10.5/supervisor/api/ingress.py): validates cookie, resolves user and replaces human headers; cookies are forwarded.
- [Supervisor cookie name](https://github.com/home-assistant/supervisor/blob/2026.10.5/supervisor/api/const.py) and [session generation](https://github.com/home-assistant/supervisor/blob/2026.10.5/supervisor/ingress.py): ingress_session and 128 lowercase hexadecimal characters.
- [Supervisor app data mount](https://github.com/home-assistant/supervisor/blob/2026.10.5/supervisor/docker/app.py) and [directory lifecycle](https://github.com/home-assistant/supervisor/blob/2026.10.5/supervisor/apps/app.py): own /data is supplied by the platform; Domus provisions only its private child.

See [native checkpoint evidence](evidence/m1-native-household-api.json) and
[original preview evidence](evidence/m1-native-ha-acceptance.json) and
[persistent owner acceptance](evidence/m1-persistent-ha-acceptance.json). These describe different artifacts/scopes.
