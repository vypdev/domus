# Home Assistant reference and acceptance matrix

Status: native authentication preview accepted on the exact owner target below on 2026-10-31.
Complete M1, standalone browser return and production compatibility remain pending.

| Target | Core | Supervisor | HA OS | Frontend | Domus acceptance |
|---|---|---|---|---|---|
| Standalone reference | 2026.10.4 | Not applicable | Not applicable | Not a server dependency | Offline fixtures pass; live browser return failed; owned OAuth grant revoked; acceptance pending |
| Owner Supervisor/Ingress reference | 2026.10.4 | 2026.10.5 | 18.3 | 20260930.5 | Edge 0.0.0-edge.1 installed and running; Open Web UI and normal Chrome reload pass with the existing HA sign-in |

The current Supervisor observation supersedes the historical 2026.10.3 value in the clarification
history. That earlier version has not passed Domus acceptance. Every other combination is unverified
until tested. Both deployment targets remain required for the first usable release.

The authorized browser entry is `/home/overview`; version observations used `/config/info`.
The earlier [read-only observation](evidence/home-assistant-reference.json) remains historical.
The owner then authorized adding the development repository and installing/starting its Edge app.
No entities, devices, automations, household records or users were changed. No credentials, private
frontend state, session cookies or HA tokens were extracted into evidence. The app remains running
for development with automatic update and start on boot disabled.

[Native acceptance evidence](evidence/m1-native-ha-acceptance.json) identifies the package/runtime
commits, checksum, safe outer browser URL, exact versions, assertions and retained app state.
The initial iframe request stalled while Chrome's task debugger was attached. Detaching that
debugger resumed loading; normal native Chrome reload also passed. No application authentication,
peer or permission boundary was weakened. The installed preview has no household database or commands.

## Required evidence before support claims

Record the exact Domus source/artifact, channel, Core/Supervisor versions, applicable protocol and
package cases, browser path, owned test records and cleanup. Keep a row pending until its cases
execute. Offline adapters and high unit coverage cannot establish Ingress cookie/peer behavior or
real deployment compatibility. A stale/missing/rejected identity must never become administrator
authority through version detection or a fallback.

See [the companion contract](../specs/platform-foundation-identity-sqlite.md) and
[implementation boundaries](architecture-identity-storage.md).

The [protocol checkpoint](ha-identity-protocol.md) has provider/loopback fixtures against the reviewed
Core schema. Those fixtures alone cannot promote a matrix row. The
[standalone authentication checkpoint](identity-household.md) adds browser-bound login and
cookie/session HTTP fixtures. A live test exchanged one delegated grant, but did not establish a
working browser session return. Shutdown confirmed revocation of that owned grant. Native preview
acceptance does not establish standalone acceptance or general support for these versions.
