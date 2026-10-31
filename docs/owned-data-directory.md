# Owned data directory

Status: the private-directory lifecycle and native persistent CLI are implemented and tested on
POSIX filesystems. The installed Edge 0.0.0-edge.1 remains the stateless connection preview. This
checkpoint does not establish writable storage for the packaged UID on the owner's Supervisor.

## Native development command

An operator first provisions one existing directory owned by the runtime user with mode 0700. Run:

```sh
domus-ingress --channel edge \
  --data-directory /owned/app-data/domus \
  --public-origin http://homeassistant.local:8123
```

The real path is operator configuration, never a browser field. Keep Stable and Edge in separate
private directories. This option generates the installation UUID only on the first valid empty
start and preserves it across restarts. It cannot be combined with --database or --instance-id.
Repeat --public-origin for configured HA origins; its existing validation still precedes data writes.
The explicit database/UUID development contract remains available independently.

The runtime must have exclusive access to this directory. A nonblocking POSIX process lock is held
until shutdown, including the listener's lifetime. Another process gets installation_in_use rather
than racing migrations or silently starting a second writer. Closing or process death releases the
lock. All entrypoints that access these files must honor the same ownership protocol.

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
explicit-database process concurrently against these files. Consistent snapshot/restore and console
recovery are still pending; no automatic backup schedule or retention is introduced.

## Verification and packaging boundary

[Evidence](evidence/m1-owned-storage.json) covers real files, another process, process death before and
after schema commit, interrupted marker replacement, restart/replay, v1 migration, strict metadata,
private permissions and refusal of missing/corrupt/foreign data. The architecture policy keeps fcntl
and other concrete I/O outside domain/application.

Supervisor supplies an app's own /data mount. The final package must provision its private child
directory for the runtime UID, preserve it on upgrade and prove that behavior on both CPU families.
The old nonroot connection-preview image does not yet do this. No package, manifest permission or
live HA data was changed in this checkpoint. See [native API](native-household-api.md),
[installed preview](installation-home-assistant.md) and [operator limits](operations-identity-storage.md).
