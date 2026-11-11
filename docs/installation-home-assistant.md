# Home Assistant app installation

Current development state (2026-11-04): Edge `0.0.0-edge.9` is installed and running on the
owner's `aarch64` Home Assistant. Through its existing HA session and Ingress, the agent created,
claimed, completed and reopened a development task, completed a second cycle, and verified the task
and saved Spanish preference after reloading. This is agent-operated acceptance on actual hardware;
human usability review and complete first-release acceptance remain separate. Stable is not yet
published. Source, package and adoption evidence are recorded in
[task workspace evidence](evidence/task-workspace.json). Historical receipts below retain their
original Edge.1–3 observations and do not describe the current installation.

## Edge.16 candidate

The Overview deadline candidate uses the Supervisor repository flow with
the [managed issue branch](https://github.com/vypdev/domus/issues/96).
The [artifact declaration](../addon-edge/artifact.json) pins the source
commit, archive and installed files. Check that Supervisor reports
`0.0.0-edge.16` before testing. The candidate uses SQLite schema 31,
introduced by Edge.13. Keep a compatible image and cold data backup before
updating from an earlier schema. When using a separate repository source,
keep existing preview data in its original app and use a disposable household
in the candidate.

## Edge.9 installation and update history

The current Edge.9 repository source, verified in Supervisor and tracked in PR #29, is:

```text
https://github.com/vypdev/domus#feature/23-complete-relative-recurrence-lifecycle-and-protected-calendar-after-the-execution-checkpoint
```

These temporary branch sources are owned by the Action. Prefer the durable development source
`https://github.com/vypdev/domus#develop` after its verified merge contains the intended version.
A published candidate on another source does not update the installed repository. Inspect the
Supervisor store's exact source, version and app slug; its GitHub homepage does not identify the
branch. A different repository URL may create a separate app with separate private data. Never
claim an in-place upgrade or data migration when installing a separate preview. Preserve the
selected backup before deliberate development data replacement; do not overwrite a managed branch
to redirect an old repository.

Edge.9 pins published runtime `93d7d77b98a196640bf0049bca36a3d90b7a5857` and archive SHA-256
`97dc46699ad7eab54c487386ffaffc28624e8e50f9d3a2f1ffc6b525fb7b8f0e`.
The [artifact declaration](../addon-edge/artifact.json) fixes all Python and compiled UI bytes.
It retains schema 9, cold backups, Ingress and the same Core API scope; no Supervisor management
API, host mount or public port is requested. Read the
[configuration, permissions and schema-9 rollback limits](../addon-edge/DOCS.md) before adoption.
The branch repository created a separate app with separate private data. A new development
household was created explicitly; the earlier Edge.7 household/preferences were not migrated into
it. Edge.7 and its selected local app backup remain the prior rollback while the next corrected
preview is prepared. No actual backup restoration is claimed. The older Edge.3 and Edge.5 apps
were uninstalled.

The later required-reason button correction is verified in current source and will ship in the
next preview. The installed Edge.9 remains fixed to the runtime above; a newer PR commit does not
silently replace its immutable application bytes.

## A local pre-update app backup

An operator can use HA's existing Terminal & SSH app. Read the installed CLI's help first;
current HA calls the commands `ha apps` and `ha backups`. The earlier `ha addons` alias remains
available on the observed system. Inspect the selected app before creating its backup:

```sh
ha apps info <installed_app_slug>
ha apps stop <installed_app_slug>
ha apps info <installed_app_slug>
ha backups new --app <installed_app_slug> --location=.local --name "Domus before update" --raw-json
ha backups info <returned_backup_slug> --raw-json
```

For an older preview such as Edge.5, record whether it was running, explicitly stop it and verify
that it is stopped before requesting the backup. Keep it stopped until the same job has completed.
Restart it with `ha apps start <installed_app_slug>` only if it was running beforehand, then inspect
its state again. If backup fails, retain the error and restore that prior running/stopped state;
do not update based only on a dispatched job. Never start a preview that was already stopped.
Edge.7 and later previews declare `backup: cold`, so Supervisor handles stopping it during a backup; expect a brief
availability interruption and fresh identity verification after restart. This is a package policy,
not evidence of an exercised owner restore. See the
[official backup configuration](https://contributors.home-assistant.io/apps/reference/configuration/#backups).

Use the exact returned backup identifier. On the observed CLI, the optional location value uses
`--location=.local`; a separate `.local` argument is rejected before a backup request is accepted.
A response containing a job ID is dispatch evidence. Inspect that same Supervisor job until it
is done with no errors, then inspect the backup metadata. Require the intended Domus version and
only the selected app, without Core or unrelated folders. An earlier owner preparation produced
one completed compressed partial backup while Edge.5 remained running. Its outer archive was readable
and its size/hash/catalog were checked, but concurrent-write consistency was not established. Keep
that observation separate from the required stopped-app pre-update capture. Private identifiers and
original device observations remain local. A subsequent selected-app capture was made after an explicit
successful stop and an independent `app_not_running_error` confirmation. Its job and all children
completed without errors. Since the app had been running beforehand, it was started afterward;
the CLI observation timed out, but a fresh app-info read confirmed Edge.5 started with its original
configuration. The start was not repeated. No owner backup was restored in that capture. Edge.7 was subsequently adopted separately.

A Supervisor app backup and a Domus console snapshot have different boundaries. The app backup
captures its application/data/configuration at one time; it does not prove that later original
operation history survives restoring that older capture. Use the supported
[console restoration protocol](restoration.md) for retaining later processed-operation fences
with a compatible current runtime. An old binary by itself cannot read schema9. Preserve the
application/data pair and later evidence before a deliberate rollback.

Official references: [store and repository endpoints](https://contributors.home-assistant.io/apps/supervisor-api/store/),
[repository installation](https://contributors.home-assistant.io/apps/guides/repository/).

## Installation journey

1. Add the selected published development source from Settings > Apps > Install app > Repositories.
2. Install the intended Domus Edge preview. Stable will have a separate published app and data.
3. Configure the exact HA browser origins, start the app and select Open Web UI.
4. Use the existing Home Assistant session. The HA app does not require another Domus login.

Standalone Docker uses HA OAuth because it runs outside Supervisor; this is a separate deployment
choice, not a prerequisite for the HA app.

## Historical issue #6 repository and Edge.1–3 receipts

The following preserves the earlier development setup and acceptance record. Use the current
preview instructions above for new work.
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
