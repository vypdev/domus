# Home Assistant app installation

Status: Edge 0.0.0-edge.3 is installed and running on the owner's HA. Its update from Edge.2,
preserved origin, existing-session access, normal Chrome reload and Domus-only restart passed on
2026-10-31. Package head 0484ba7 passes every CI group, including all 15 image cases on native amd64
and aarch64. The complete UI, live household/recovery/restore and production release remain pending.
[Edge.3 owner acceptance](evidence/m1-edge3-ha-acceptance.json) is separate from the earlier
[persistent Edge.2 receipt](evidence/m1-persistent-ha-acceptance.json) and Edge.1 preview.

## Intended user journey

1. Add the published Domus app repository from Settings > Apps > Install app > Repositories.
2. Install Domus Edge for development, or the separately published stable app for production.
3. Configure the HA browser origins, then start and select Open Web UI. Optionally enable its sidebar entry.
4. Use the existing Home Assistant session. There is no second Domus sign-in or password.

The independent Docker installation has a separate OAuth journey because it runs outside the
Supervisor. That journey is not an installation prerequisite for the HA app.

## Reviewed development repository

For the issue #6 preview, copy this exact branch URL into the HA repository dialog:

```text
https://github.com/vypdev/domus#feature/6-implement-home-assistant-identity-and-sqlite-platform-persistence
```

This is a disposable development repository, not the permanent production channel. The Action owns
the branch lifecycle. The owner has retained its app for continued development. Remove the owned
test app/repository when that testing ends; production installation
must use the eventual published stable repository. Do not add the default repository URL yet:
the default branch does not contain this preview package.

The development package is Domus Edge 0.0.0-edge.3, now installed after a deliberate owner-target
update from Edge.2. Supervisor builds the app locally and verifies its immutable runtime
archive before extracting it; the exact pins are recorded below. The original Edge.1 used runtime
98bd12f1bf141ba64053730b2686bd848aee1b1c.
Python/uv image digests and the dependency lock are fixed. No registry login is needed.

The installed app is `62fdc661_domus_edge`. Open it at
[Domus Edge in the owner's HA](http://homeassistant.local:8123/app/62fdc661_domus_edge).
The connection preview, including a normal reload, passed on Core 2026.10.4, Supervisor 2026.10.5,
HA OS 18.3 and Frontend 20260930.5. Start on boot, watchdog and automatic updates remain disabled.
[The native acceptance receipt](evidence/m1-native-ha-acceptance.json) records the bounded scope.
It does not claim that later source changes are in this immutable-source image.

## Original Edge.1 preview

The preview runs with `domus-ingress --channel edge` inside the Supervisor container. Configuration
supplies SUPERVISOR_TOKEN privately; no human enters or copies a token. The private listener accepts
protected requests only from the actual Supervisor peer, validates the Ingress base path and exact
subject header, and checks that human in Core. Forwarding headers, names and the transport account's
administrator privilege cannot grant the requesting person access.

The root page shows connection status, uses relative navigation and requires no browser cookie or
OAuth callback. The identity endpoint exposes only the requesting human's proof. Process health
is available to Supervisor and container loopback and is not a claim of HA availability. There are
no household commands, local read-grace sessions or business database in this preview. A failed fresh
proof blocks access. It is not complete M1, the product UI or a production compatibility claim.

The Edge manifest enables Ingress and Core API access, publishes no host port and requests no
Supervisor management API or host mounts/privileges. Stable and Edge must remain distinct apps with
separate data when Stable is published. Core API access gives the container a technical HA
administrator credential; it must stay private and must never substitute for the human principal.

The first preview is deliberately stateless and runs as UID/GID 65532. It does not establish persisted
installation identity, household setup, backup behavior or production acceptance. Container tests use
fictional tokens with networking disabled, exercise the real listener and remove only their own
temporary containers. The original source remains identified in its historical receipt; current
review/rollback images are Edge.3 and Edge.2.

The later [persistent native API](native-household-api.md) is a tested development CLI with SQLite,
bounded Ingress sessions and the shared household routes. Edge.2 now packages it with private data and automatic identity. Product UI and live household/recovery
acceptance remain pending; the earlier preview evidence does not establish those later services.

## Persistent Edge.2

Edge 0.0.0-edge.2 now packages immutable runtime d013cf2c8b932d0e00f5858053cbc0e663d5eee1,
archive SHA-256 fa58d457bef8a863a1943b4e6ba5c9513da8d3baa8b0a033bdcbe7bf11b09c6c.
The owner update and configured startup are now verified; source preparation and image checks remain
separate from the bounded [live receipt](evidence/m1-persistent-ha-acceptance.json).

In the app Configuration tab, set public_origins to one to four exact URLs used to open HA, including
scheme and port when present, for example http://homeassistant.local:8123. No paths or credentials.
The default empty list refuses startup; there is no permissive fallback or request-derived origin.
This is a one-time configuration, not another sign-in. Restart after changing it. The breaking-version
marker prevents an automatic update from crossing this new configuration boundary.

The container starts a fixed-path launcher as root to provision only /data/domus, then clears groups
and execs the server as UID/GID 65532. Existing private data is validated without recursive repair.
No host port, mount, capability, management API or protection-mode change is requested. A new empty
installation persists its UUID/channel and SQLite schema before listening, without creating a home.
Identity, household records and operation receipts survive restart; sessions are memory-only. The
initial page is still a connection preview. Household/member/policy/recovery APIs are now packaged,
while the complete interface, restore activation and live household/recovery operations remain pending.

Local isolated arm64 tests verify process IDs/groups/capabilities, private ownership, inability to
regain root, forged-direct-request rejection, shared console attachment, an excluded second runtime
and one-effect original-command replay after restart. Storage records use a fictitious test authority;
these tests do not prove a live human sign-in. Both native CPU-family CI checks also pass. Owner
Chrome/Ingress access, normal reload and app restart pass separately; household commands, outage
behavior and recovery were not exercised on the owner's HA. See [package evidence](evidence/m1-persistent-app-package.json)
and [private data lifecycle](owned-data-directory.md).

Official references: [Ingress authentication and relative paths](https://contributors.home-assistant.io/apps/guides/ingress/),
[repository installation and branch selection](https://contributors.home-assistant.io/apps/guides/repository/),
[Core API proxy permissions](https://contributors.home-assistant.io/apps/guides/communication/).

## Restoration-capable Edge.3

Edge 0.0.0-edge.3 pins runtime faa1654a5c9cddb562bfcd4c02d4cebfeb78e9f5 and archive SHA-256
15bcd701696204b3362cebe5901feb3d0072c9bac1db2ef2cbc5007e9ed73717. Its source archive was compared
byte for byte against all 272 tracked files of that commit. The default Supervisor folder builds
the pin with frozen dependencies; no test-only runtime override is needed.

It adds schema-4 retained history and the [console restoration protocol](restoration.md). Local real
arm64-image tests use SQLite 3.46.1, exercise both runtime compositions, snapshot/prepare/inspect/
activate/status/resume, later-history rollback, process death and startup refusal while pending.
The actual previous Edge.2 image upgrades through schema 3 to 4 while keeping UUID and original
operation replay. Its pre-upgrade snapshot remains independently inspectable and restorable into
a migrated new generation. Edge.2 refuses both a flat schema 4 and selected generations without
changing any file. An older image alone is not a valid rollback for newer data.

The every-PR CI builds both the current and immutable previous image on native amd64 and aarch64
and runs the same 15 container cases. Current package-head CI is separate evidence from the
pre-publication local run. [Package evidence](evidence/m1-restoration-app-package.json) records exact
sources and assertions. A subsequent [owner update](evidence/m1-edge3-ha-acceptance.json) verifies
Edge.3 installed/running, preserved origin and existing-session access after reload/restart. No live
restoration was performed; complete restore acceptance is separate from this connection-page proof.
