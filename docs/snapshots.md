# Manual SQLite snapshots

Status: local snapshot creation and inspection are implemented, with real SQLite/ASGI-era business
records, private filesystem checks and a console entrypoint. Pure restore reconciliation and private
blocked preparation/inspection, runtime history/replay and recovery guards are now tested locally;
verified offline activation remains pending. The owner's installed persistent Edge 0.0.0-edge.2 is
unchanged by this increment.
No automatic backup frequency, rotation or retention is introduced.

## Create a snapshot

Run the console as the runtime UID that owns the data. For a ready managed data directory in either mode:

```sh
domus-admin --channel edge --data-directory /data/domus \
  snapshot create /data/snapshots/manual-001
```

The destination parent must already exist, be owned by that UID and permit its writes. Provisioning
those package directories remains separate work. The destination must be new and outside the owned
source directory. For an explicit standalone installation:

```sh
domus-admin --channel edge --database /owned/data/domus.sqlite3 \
  --instance-id <persisted-installation-uuid> \
  snapshot create /owned/backups/manual-001
```

The command creates one private directory containing exactly:

| File | Contents |
|---|---|
| domus.sqlite3 | Consistent committed business schema, identity, household/member/policy state, receipts, audit, outbox and recovery records |
| installation.json | Matching ready installation UUID/channel metadata |
| manifest.json | Format/schema versions, snapshot ID, capture/last-command timestamps, database size and SHA-256 hashes |

The manifest is written last after database validation, hashing and file flushes; success also waits
for directory flushes. Existing destinations are never overwritten, including incomplete earlier
attempts. An interrupted/failed creation may leave private diagnostic files without a valid manifest.
Inspect before retrying or deliberately cleaning only that owned failed destination. Output failure
after publication reports uncertainty rather than claiming the snapshot was not created.

The source is read through SQLite's backup API within a pinned read transaction. Real-file tests
show that a concurrent WAL writer can commit a later revision while the archive retains the earlier
coherent view. A long read can delay writers in rollback-journal mode; ordinary bounded busy/retry
rules still apply. No source business change or new household is made by snapshot creation.

## Inspect independently of the active database

Use the expected persisted installation UUID and channel, even if the active database is unavailable:

```sh
domus-admin --channel edge --instance-id <persisted-installation-uuid> \
  snapshot inspect /owned/backups/manual-001
```

Inspection does not require or open an active source selection. It verifies exact bundle membership,
private ownership/modes, regular singly linked files, strict bounded manifest/identity metadata,
hashes/size, compatible schema definition, physical integrity, foreign keys, business record shapes
and atomic receipt/audit/outbox linkage. Wrong installation/channel, changed bytes, incomplete files,
special files and corrupt records are rejected. Inspection never migrates the archive. Compatible
historical schema 1/2 fixtures are inspected in place; capture currently requires the initialized
current schema 3. Credentials and session leases are not stored in those business schemas or collected
from environment, browser, app configuration or other directories.

The capture timestamp is the local UTC reading at the selected database view. last_committed_at is
the greatest retained receipt timestamp, or null before any command. Both are Unix milliseconds.
The snapshot ID and database hash identify the exact captured artifact. A verified archive is not an
activated restore, a package compatibility claim or evidence of writes after that checkpoint.

The default logical deadline is 30 seconds; --timeout accepts a finite positive value up to 3600:

```sh
domus-admin --channel edge --instance-id <persisted-installation-uuid> \
  snapshot --timeout 60 inspect /owned/backups/manual-001
```

Deadline checks run between copy/hash steps and through SQLite's query progress handler. Checksums
detect changed bytes; the local operator and private directory remain the trust boundary. Keep the
whole bundle private and intact. Managed-directory creation attaches through the shared maintenance guard;
inspection needs no HA token or additional HA authorization. No HTTP backup endpoint is exposed.

See [source-identified evidence](evidence/m1-snapshots.json), [owned data](owned-data-directory.md),
[migrations](migrations-identity-storage.md) and [operator limits](operations-identity-storage.md).
The restore flow must still preserve the selected checkpoint and replay safeguards before activation
in a new matching directory, with writes stopped. The owner accepted [A30](decisions.md): restore the
checkpoint's state while retaining readable later receipts/history as already processed, without
executing their effects again. [Preparation](restoration.md) seals those facts beside the original
checkpoint, without importing them into runtime storage or enabling activation yet.

Implementation references: [Python sqlite3 backup interface](https://docs.python.org/3.14/library/sqlite3.html#sqlite3.Connection.backup)
and [SQLite backup semantics](https://www.sqlite.org/backup.html). The inspected local runtime is
Python 3.14.6 with SQLite 3.53.3; current Python 3.14 documentation is independently versioned.
