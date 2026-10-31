# Home Assistant reference and acceptance matrix

Status: pending application acceptance. The owner's HA was inspected read-only in Google Chrome
on 2026-10-31. Version visibility is not a verified Domus API principal or a packaged-runtime test.

| Target | Core | Supervisor | HA OS | Frontend | Domus acceptance |
|---|---|---|---|---|---|
| Standalone reference | 2026.10.4 | Not applicable | Not applicable | Not a server dependency | Offline protocol fixtures pass; API/session wiring, package and live proof pending |
| Owner Supervisor/Ingress reference | 2026.10.4 | 2026.10.5 | 18.3 | 20260930.5 | Pending implemented artifact, package and live/browser cases |

The current Supervisor observation supersedes the historical 2026.10.3 value in the clarification
history. That earlier version has not passed Domus acceptance. Every other combination is unverified
until tested. Both deployment targets remain required for the first usable release.

The authorized browser entry is `/home/overview`; the version observation used `/config/info`.
No credentials, private frontend state or HA tokens were extracted. No entity, device, automation
or HA configuration was changed. [Observation metadata](evidence/home-assistant-reference.json)
contains versions and scope only.

## Required evidence before support claims

Record the exact Domus source/artifact, channel, Core/Supervisor versions, applicable protocol and
package cases, browser path, owned test records and cleanup. Keep a row pending until its cases
execute. Offline adapters and high unit coverage cannot establish Ingress cookie/peer behavior or
real deployment compatibility. A stale/missing/rejected identity must never become administrator
authority through version detection or a fallback.

See [the companion contract](../specs/platform-foundation-identity-sqlite.md) and
[implementation boundaries](architecture-identity-storage.md).

The [protocol checkpoint](ha-identity-protocol.md) has provider/loopback fixtures against the reviewed
Core schema. It does not promote either matrix row to supported or establish real HA authentication.
