# Identity and household access

Status: standalone authentication and a native HA authentication preview are implemented. Household setup,
enrollment/member/policy commands, recovery, product UI and Supervisor local read-grace sessions remain
pending. SQLite member/policy storage and the pure authorization rules have independent tests.

## Home Assistant app

Open the installed app through HA's Open Web UI or sidebar entry. Ingress uses the existing HA
session; no additional Domus login is required. See [app installation](installation-home-assistant.md)
for the current preview and outstanding packaging/installation evidence.

## Independent Docker sign-in

Open the configured Domus `/api/v1/auth/start` URL. Home Assistant authenticates your own HA account
and authorizes the local Domus client. Domus receives a delegated HA credential with your HA account's
permissions; this checkpoint uses it to verify identity and to refresh/revoke its own grant. Passwords
are entered only into HA. No local password, shared PIN, person entity or submitted member ID signs in.

The browser returns to the fixed callback. A five-minute server-side attempt checks state, S256 PKCE
and a private browser binding before its single use. Invalid, expired, duplicate or wrong-browser
attempts cannot exchange a code. A declined authorization consumes the bound attempt without access.
If the browser binding is missing, invalid or expired, the error explains how to restart at
`/api/v1/auth/start` and finish within five minutes. It never exchanges an unbound callback code.
The callback redirects to `/api/v1/session`, removing code/state from the final URL. That response
contains verified identity and the current access state; it contains no HA token or session cookie.

`ha_administrator` describes HA proof. It is not a Domus household grant. Arriving first or signing in
does not create a household, enroll a member or become its administrator. The explicit setup/member
journeys must still apply the [accepted mappings and permissions](../specs/household-identity.md).

## Current state and next action

| State | Meaning | Next action |
|---|---|---|
| Authenticated, full | Fresh HA proof and a valid original session | Use permitted functions; household policy still governs each protected action |
| Authenticated, read_only | HA is unavailable; the original session has not expired | Query permitted local data; reconnect to HA before changes |
| Blocked / sign-in required | Session absent/expired, identity rejected or browser binding invalid | Start a new sign-in if eligible |
| Logged out | Local cookie, lease and private credential have been removed | No action if remote revocation is confirmed; review HA authorization if unconfirmed |

Current local membership, suspension and policy remain authoritative for protected household reads
and writes. Fresh HA proof is required for mutations; an outage cannot renew a session or grant new
rights. Explicit rejection destroys local access rather than becoming outage grace. Restart requires
sign-in again; household records and actor history remain separate durable data.

## Sign out

The application first obtains a session-bound nonce from `/api/v1/auth/csrf`, then posts an empty JSON
object to `/api/v1/auth/logout` with that X-CSRF-Token and the exact configured Origin. Local logout
works during an HA outage. Its response distinguishes confirmed, failed and unknown upstream
revocation; unknown is never reported as success. It does not sign out the parent HA frontend.

HA credentials/session material live only in bounded process memory, are omitted from diagnostic
representations and never enter business SQLite tables, audit, outbox or snapshots. See the
[configuration](configuration.md), [operator guide](operations-identity-storage.md),
[protocol contract](ha-identity-protocol.md) and [reference matrix](compatibility-home-assistant.md).
