# HA identity protocol adapters

Status: fixed endpoint configuration, OAuth form transport, correlated WebSocket proof and the
Supervisor identity boundary are implemented as adapters. Authentication entrypoints, bounded
single-use browser attempts, credential/session wiring and live/package acceptance remain pending.
Do not expose these private adapters directly as endpoints that accept a submitted token or actor.

## Standalone

Only operator configuration supplies the HA origin and Domus public origin. Origins reject paths,
userinfo, query/fragment delimiters, whitespace, invalid hosts/ports and ambiguous escape syntax.
The public Domus origin requires HTTPS; explicitly enabled development HTTP is limited to loopback.
The owner's configured LAN HA HTTP origin is supported as a configured upstream. Request Host,
forwarding metadata and callback parameters cannot replace either origin.

The client ID is the fixed Domus origin with a trailing slash; the callback is that origin plus
`/api/v1/auth/callback`. Code exchange sends an URL-encoded authorization-code grant with the exact
client ID and S256 verifier. Refresh uses the same client ID; revoke uses `/auth/revoke`. The HTTP
adapter disables redirects and environment proxies, retains TLS verification, refuses unsolicited
content encoding, bounds decoded responses and redacts transport errors/token representations.

The next browser/application boundary must issue and atomically consume state, PKCE and a browser-bound
attempt, perform Origin/CSRF validation, retain credentials privately in memory and issue a bounded
server-owned session. There is no caller-supplied bearer-token login route in this checkpoint.

`auth/current_user` proves the exact user ID and exact boolean administrator flag. Its schema does
not contain active/system-generated flags. The adapter therefore requires a server-exchanged
client-bound OAuth grant and a matching nonempty credential provider list. Core 2026.10.4 enforces
active users during authentication and refuses system users when creating client-bound refresh
tokens. A raw Supervisor or long-lived transport token is not a substitute for this provenance.
Constructing the internal `OAuthTokens` value does not authenticate a browser.

## Supervisor / Ingress

The fixed WebSocket URL is `ws://supervisor/core/websocket`. The Supervisor token is a private
transport credential; its own administrator status never identifies the requesting person.
`SupervisorIdentity` requires the actual socket peer `172.30.32.2`, exactly one case-insensitive
`X-Remote-User-Id` and a fresh Core directory lookup of that exact ID. Names, display names,
forwarding headers and X-Ingress-Path cannot establish identity or a role. Duplicate, malformed,
missing and mismatched subjects fail closed before protected effects.

The Core `config/auth/list` schema supplies active/system-generated flags, `is_owner` and group IDs.
The exact target must be active and non-system. An exact boolean owner or membership in
`system-admin` establishes administrator status; another row's privilege never transfers to the target.
Directory permission denial is distinct from rejecting the requesting user's own authentication.

Server/package wiring must still prove the private listener, absence of a direct published port,
disabled proxy-header rewriting, validated UI base path and session/subject binding. Ingress uses
HA's native authentication rather than adding a second OAuth login. Core logout, Ingress cookie
expiry and Domus session expiry are separate contracts; no instant global logout claim is made here.

## Resource and implementation contract

| Boundary | Bound |
|---|---|
| HTTP or WebSocket operation | Five-second async deadline, including protocol I/O |
| HTTP connect / read inactivity | Two / three seconds |
| WebSocket opening / closing | Two seconds / 250 ms |
| Protocol document or frame | 65,536 bytes |
| Token text / authorization code | 8,192 / 4,096 ASCII characters |
| PKCE verifier | 43–128 RFC-compatible characters |
| Credential rows / directory rows / groups | 32 / 256 / 32 |
| HA user ID | Exactly 32 lowercase hexadecimal characters |

Adapters expose synchronous facades for synchronous application workers; each owns its async I/O
lifetime. Future ASGI wiring must use those workers rather than nesting `asyncio.run` in a running
event loop. Business policy and transactions remain independent of HTTP, WebSocket and these limits.

HTTPX 0.28.1 and websockets 17.4 are locked with their transitive dependencies. Existing dependency
versions are retained; the resolver also refreshed available wheel metadata. A pinned WebSocket
redirect hook returns the original handshake failure. Real loopback redirect fixtures prove that
the second origin is never contacted. The client uses an isolated disabled wire logger so debug
logging cannot record authentication frames. Library upgrades must retain these negative contracts.

## Evidence and limitations

Tests use fictional tokens/users, HTTPX provider fixtures and disposable WebSocket servers listening
only on loopback. They cover correlation/type checks, admin/owner distinction, technical and inactive
subjects, source mismatch, malformed/oversized content, denial versus unavailability, deadline
cancellation, cleanup, redirect refusal and token redaction. The deadline fixtures expire immediately
without business sleeps. No fixture logs into or modifies the owner's HA.

See [source-identified protocol evidence](evidence/m1-ha-protocol.json),
[the HA reference matrix](compatibility-home-assistant.md) and
[the full M1 contract](../specs/platform-foundation-identity-sqlite.md).

Primary references: [HA authentication API](https://contributors.home-assistant.io/core/internals/auth-api/),
[Core 2026.10.4 OAuth/current-user implementation](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/auth/__init__.py),
[client-bound token restrictions](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/auth/__init__.py),
[directory schema](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/config/auth.py),
[administrator semantics](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/auth/models.py),
[Supervisor communication](https://contributors.home-assistant.io/apps/guides/communication/) and
[Ingress boundary](https://contributors.home-assistant.io/apps/guides/ingress/).
