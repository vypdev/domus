# Home Assistant app installation

Status: native Ingress authentication preview and source-bound Edge app package implemented.
Local arm64 container tests and both native CPU families in CI pass for package commit
650f1517f0e15664ea455628e63154dada0414f2. Edge 0.0.0-edge.1 is installed and running on the owner's
HA; Open Web UI and normal Chrome reload use the existing HA session successfully. No production
release is available; the complete product remains under development.

## Intended user journey

1. Add the published Domus app repository from Settings > Apps > Install app > Repositories.
2. Install Domus Edge for development, or the separately published stable app for production.
3. For Edge.2, configure the HA browser origins, then start and select Open Web UI. Optionally enable its sidebar entry.
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

Select Domus Edge 0.0.0-edge.1. Supervisor builds the app locally; the Dockerfile fetches immutable
runtime commit 98bd12f1bf141ba64053730b2686bd848aee1b1c and verifies its SHA-256 before extracting it.
Python/uv image digests and the dependency lock are fixed. No registry login is needed.

The installed app is `62fdc661_domus_edge`. Open it at
[Domus Edge in the owner's HA](http://homeassistant.local:8123/app/62fdc661_domus_edge).
The connection preview, including a normal reload, passed on Core 2026.10.4, Supervisor 2026.10.5,
HA OS 18.3 and Frontend 20260930.5. Start on boot, watchdog and automatic updates remain disabled.
[The native acceptance receipt](evidence/m1-native-ha-acceptance.json) records the bounded scope.
It does not claim that later source changes are in this immutable-source image.

## Current native preview

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
temporary containers. The image remains available locally as the current review/rollback artifact.

The later [persistent native API](native-household-api.md) is a tested development CLI with SQLite,
bounded Ingress sessions and the shared household routes. It has not replaced this installed preview.
App data ownership, automatic installation identity and product UI must be packaged and verified
before those later services can be accepted through this installation journey.

## Persistent Edge.2 candidate

Edge 0.0.0-edge.2 now packages immutable runtime d013cf2c8b932d0e00f5858053cbc0e663d5eee1,
archive SHA-256 fa58d457bef8a863a1943b4e6ba5c9513da8d3baa8b0a033bdcbe7bf11b09c6c.
The owner still has Edge.1 until an explicit update is performed and verified. Source preparation
is not installed-runtime evidence.

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
while the complete interface, restore activation and live acceptance remain pending.

Local isolated arm64 tests verify process IDs/groups/capabilities, private ownership, inability to
regain root, forged-direct-request rejection, shared console attachment, an excluded second runtime
and one-effect original-command replay after restart. Storage records use a fictitious test authority;
these tests do not prove a live human sign-in. Both native CPU-family CI checks and updated owner
Chrome/Ingress acceptance are separate gates. See [package evidence](evidence/m1-persistent-app-package.json)
and [private data lifecycle](owned-data-directory.md).

Official references: [Ingress authentication and relative paths](https://contributors.home-assistant.io/apps/guides/ingress/),
[repository installation and branch selection](https://contributors.home-assistant.io/apps/guides/repository/),
[Core API proxy permissions](https://contributors.home-assistant.io/apps/guides/communication/).
