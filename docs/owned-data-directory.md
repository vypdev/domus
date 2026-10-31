# Owned data directory

Status: the private-directory lifecycle and both persistent CLIs are implemented and tested on
POSIX filesystems. Edge 0.0.0-edge.2 is installed on the owner's Supervisor and passes configured
start, existing-session access, normal reload and restart. [Owner evidence](evidence/m1-persistent-ha-acceptance.json)
records that bounded scope; real-image storage/replay evidence is separate from live household commands.

## Runtime commands

An operator first provisions one existing directory owned by the runtime user with mode 0700. Run:

```sh
domus-ingress --channel edge \
  --data-directory /owned/app-data/domus \
  --public-origin http://homeassistant.local:8123
```

The independent runtime uses the same storage protocol without a manually supplied UUID:

```sh
domus-server --ha-url http://homeassistant.local:8123 \
  --public-origin https://domus.example --channel edge \
  --data-directory /owned/app-data/domus
```

For loopback development, use --public-origin http://127.0.0.1:8099 and --development-http. That
option requires a loopback listener. The standalone server still authenticates each user through HA;
persisting installation identity does not persist authorization tokens or sessions. Native Ingress
continues using the existing HA session without another login. Both compositions share the same
household use cases; these commands do not implicitly create a household or member.

The real path is operator configuration, never a browser field. Keep Stable and Edge in separate
private directories. This option generates the installation UUID only on the first valid empty
start and preserves it across restarts. It cannot be combined with --database or --instance-id.
Repeat --public-origin for configured HA origins; its existing validation still precedes data writes.
The explicit database/UUID development contract remains available for independent files. Both native
and standalone explicit-file runtimes reject installation, generation, snapshot, restore or activation
metadata and operations.jsonl entries in the parent directory, including broken symlinks, before SQLite.
They cannot bypass owned-directory or partial-restore lifecycle guards.

The runtime must have exclusive access to this directory. A nonblocking POSIX process lock is held
until shutdown, including the listener's lifetime. Another process gets installation_in_use rather
than racing migrations or silently starting a second writer. Closing or process death releases the
lock. All entrypoints that access these files must honor the same ownership protocol.

Startup holds maintenance.lock exclusively during initialization/migration, then retains a shared
guard while serving. [Console approval](administrator-recovery.md) attaches to ready matching data
with another shared guard, without migration, UUID generation or a second server lease. It can run
alongside the one server. An active console attachment prevents startup migration until it closes.
The explicit-file console applies the same owned-marker refusal.

## Durable states

| State | Startup behavior |
|---|---|
| Empty private directory | Persist a new UUID/channel marker in initializing state, then initialize schema and publish ready before starting HTTP. No household/member is created. |
| Initializing marker | Resume only that persisted UUID. An interrupted schema transaction or committed empty schema can complete initialization; a conflicting/corrupt database is rejected. |
| Ready marker and matching database | Validate existing schema/installation before mutation, permitting the explicit compatible versioned migration. Reuse identity and durable business/replay records. |
| Ready marker with missing/empty/replaced database | Stop. Never regenerate a UUID or create a replacement empty database. |
| Database, sidecar or staged identity without marker | Stop. Never adopt it as a new installation. |
| Wrong channel, invalid metadata or unexpected artifact | Stop and retain existing records for deliberate operator investigation. |

The identity marker is bounded strict JSON with exact fields and a version. Its first write and
subsequent atomic replacement are flushed and directory-synced. A failed first marker write may
require operator recovery; Domus never treats partial metadata as permission to invent another UUID.
A fully owned abandoned staging file can be discarded under the process lock. Existing UUID/channel
metadata remains authoritative. No HTTP listener is started until initialization returns ready.

Files must be regular, singly linked, owned by the runtime UID and mode 0600. Directory/file opens
reject symlinks; FIFOs and other special files are rejected without waiting for a writer. No recursive
permission repair, traversal of arbitrary files or adoption of group/world-readable data occurs.
The directory and its parents remain a trusted local-operator boundary; this does not protect against
that operator replacing paths or editing metadata. The protocol does not authorize manual repairs.

SQLite, installation metadata and replay evidence form one operational unit. Do not delete the marker
to resolve a startup failure, copy a database alone into an empty directory, or run a standalone
explicit-database process concurrently against these files. [Manual snapshots](snapshots.md) can be
created and inspected. Offline console restoration is implemented locally; actual package/deployment
acceptance remains pending. No backup schedule or pruning is introduced.

## Selected generations

The new source runtime also reads a strict format-2 root identity selecting one generation ID under
the fixed generations directory. This is filesystem identity format 2, independent of business
SQLite schema 4. Existing flat format-1 installations retain their normal behavior and are not
silently converted by startup. The offline activator publishes a verified selection only after
exclusive source validation and target preparation. Do not construct or edit these files manually.

The selected private slot contains domus.sqlite3, a ready format-1 installation.json and a
generation.json matching the root selection. UUID/channel and exact selection must agree. Root-level
runtime/maintenance guards still protect the entire installation. Startup rereads selection after
acquiring the guards, so an earlier observation cannot select stale data. A missing, empty, foreign,
pending or unsafe slot fails; retained flat data is never a fallback or a source for empty replacement.
Managed startup, console attachment and explicit-file factories refuse direct slot bypass, including
a generation marker whose ordinary identity is missing.

An optional private archives directory is recognized beside generations, outside the selected
database's directory. Real-file tests create and inspect snapshots and blocked restore preparations
there while console attachment shares the runtime's maintenance guard. Symlinked generation/slot/
archive directories fail. Both composed APIs retain the selected household and original receipt
across restart, leaving retained flat bytes unchanged. A prepared restore publishes its blocked
identity before copying database bytes; rejected startup does not add lock files to it.

The console activator holds both root leases exclusively, revalidates bound source history, captures
a source-checkpoint and imports/migrates only a blocked new slot before publishing the root selection.
Pending activation metadata blocks all startup; resume finishes the same durable transition.
The activations directory retains sealed inputs, rollback snapshots and immutable completion receipts.
Actual-image/deployment restore acceptance remains pending. See
[offline activation](restoration.md), [activation evidence](evidence/m1-offline-activation.json),
[generation evidence](evidence/m1-generation-selection.json) and the
[complete restoration contract](../specs/platform-restoration.md). The installed Edge.2 remains unchanged.

## Verification and packaging boundary

[Evidence](evidence/m1-owned-storage.json) covers real files, another process, process death before and
after schema commit, interrupted marker replacement, restart/replay, v1 migration, strict metadata,
private permissions and refusal of missing/corrupt/foreign data. The architecture policy keeps fcntl
and other concrete I/O outside domain/application.
The [explicit-file boundary evidence](evidence/m1-explicit-storage-boundary.json) additionally covers
both runtime factories against active and closed owned directories without changing database bytes.
The [standalone composition evidence](evidence/m1-standalone-owned-storage.json) covers automatic
identity, original-operation replay, session loss on restart, channel separation, one initialization
per startup and lease release after composition/listener/shutdown failures. Snapshot and recovery
console attachment uses --data-directory for either mode.

Supervisor supplies an app's own /data mount. The final package must provision its private child
directory for the runtime UID, preserve it on upgrade and prove that behavior on both CPU families.
The original nonroot Edge.1 preview did not do this; Edge.2 now packages the launcher and passed
both native CPU-family container checks and owner startup/restart. See [native API](native-household-api.md),
[installed preview](installation-home-assistant.md) and [operator limits](operations-identity-storage.md).

### Packaged launcher preparation

domus-ha-app --channel edge prepares the Supervisor package, using only the fixed /data path.
It validates the Supervisor token and bounded /data/options.json before creating anything. That file
contains only public_origins: one to four distinct HA browser origins. It never accepts a data path,
command, UID or credential from a browser. Existing native sessions still supply human authentication.

The launcher starts as container root only to create /data/domus for UID/GID 65532. An existing child
must already have that owner/group and mode 0700. It never recursively changes ownership or repairs
existing data. An interrupted ownership step may require explicit operator investigation; no existing
files are adopted. The root-owned /data parent and options must not be writable by group/others.
Symlinks, special options files and multiply linked options fail.

Before executing the fixed Ingress entrypoint, it clears supplementary groups, sets GID/UID 65532,
checks all real/effective IDs and passes only a fixed environment with the private Supervisor token.
There is no root server fallback. The owned-directory protocol then governs SQLite. The installed
Edge.2 image uses this launcher. [Unit evidence](evidence/m1-ha-app-bootstrap.json) is distinct from
the [real-image kernel checks](evidence/m1-persistent-app-package.json) on both CPU families and the
bounded owner acceptance. Live household/recovery/restore acceptance is not inferred from startup.
