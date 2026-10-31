# Checkpoint restoration and retained history

Status: pure reconciliation and private SQLite preparation/inspection are implemented and tested
locally on issue #6. Schema-4 runtime history/replay and recovery guards are tested with synthetic
offline fixtures. **Production activation remains pending.** There is no restore
console command or HTTP endpoint yet. The installed Edge.2 image remains unchanged. This work does
not complete M1 or validate a restoration on the owner's Home Assistant.

The owner accepted [A30](decisions.md): select the checkpoint's business state while preserving
readable later receipts and history as already processed. Retaining history must prevent duplicate
effects without silently restoring newer business changes.

## Implemented preparation

The application uses a semantic preparation/inspection port. Domain rules contain no SQL, paths,
frameworks or clocks. The SQLite adapter independently verifies the selected manual snapshot and
reads current complete operation evidence in one committed transaction. A concurrent WAL writer
does not change that selected source view. Preparing while writes continue does not authorize later
activation: activation must stop writes and prove the source binding is still current.

The output must be a new private destination with an existing trusted parent. Preparation never
overwrites complete or partial output, replaces the active source or migrates the checkpoint. It
copies exact snapshot database bytes and seals four files:

| File | Meaning |
|---|---|
| domus.sqlite3 | Original checkpoint database, with its verified schema and checksum |
| installation.json | Same installation UUID/channel with state restore_pending |
| operations.jsonl | Complete selected/current operation projection, including retained later facts |
| restore.json | Format-1 prepared manifest; written last after data verification and flush |

Each directory is mode 0700; files are owner-only regular single-link mode 0600. No-follow, bounded
strict parsing, exact inventory, logical deadline and checksum checks apply. Checksums detect changed
bytes; they do not replace the local owner's trust boundary. The manifest binds the original
checkpoint, source-frontier digest, journal/identity hashes, total/current counts and position high-water.

Managed startup and console attachment reject complete or journal-bearing partial candidates before
creating runtime lock files. The blocked identity is written before database bytes, and both
explicit-file runtime factories reject every managed identity/journal/generation signal.
An incomplete candidate never becomes an implicit empty installation. Removing metadata manually
is unsupported and would discard its safety protocol.

## Reconciliation rules

Every retained operation includes its original command scope, canonical payload fingerprint, result,
operation ID/time, audit detail, event payload, position and actual acknowledgement. Conflicting facts
for one scope, operation ID or position fail. The checkpoint must be fully explained by current
evidence and must not omit an earlier retained position. Wall-clock timestamps do not prove ancestry.

Checkpoint operations remain current. Source-only operations become historical and retain their
first archival provenance. Selecting a known historical operation again can make it current without
another execution. Acknowledgements can progress from false to true; they cannot regress. Historical
suppression does not fabricate a delivery acknowledgement.

The journal is ordered by household/actor/action/command key. Payloads are streamed; uniqueness
sets for operation IDs and positions grow with the history size. Each line is bounded to 262,144
bytes, accommodating three independently bounded 65,536-byte JSON objects plus fixed metadata.
Parsing rejects duplicate keys, invalid UTF-8, oversized/deep input and malformed evidence.

An independent inspector requires only the output and expected UUID/channel. It validates exact
files/hashes/size, blocked identity, compatible schema/integrity/atomic records, checkpoint projection,
counts and high-water. It does not need the live source or imply that source is still unchanged.

## Failure and unfinished work

Conflicts or copy/validation failures leave source data intact and retain private partial output.
An error or deadline after manifest publication reports uncertainty; inspect that same target rather
than retrying into it. Never claim that an output error proves no artifact was written.

Preparation keeps checkpoint schema 1, 2, 3 or 4 unchanged. Later acknowledgements and rolled-away
facts remain sealed in the journal until a future verified activation flow imports them. The current
preparation command does not migrate or activate the candidate.

## Implemented runtime history

Schema 4 adds retained_operations without a current-household foreign key. An infrastructure-only
import validates complete original facts, selected current projection, prior history, first archive
provenance and sequence continuity. It requires an existing caller-owned transaction and uses a
savepoint, so an error cannot leave partial changes even if the caller subsequently commits. Normal
application ports cannot select an archive or invoke import. Migration from frozen schemas 1/2/3
is additive and transactional; failure retains the original schema and bytes.

Current receipt lookup falls back to retained history. It still checks current authorization before
replay/disclosure, returns the original result and conflicts on changed payload. Projection metadata
does not enter original complete evidence. Both standalone and native APIs return state=historical
and archived_by for rolled-away work, with an explicit message that its effect is absent from current
state. A historical event has delivery=suppressed unless it was actually acknowledged, in which case
delivery=delivered preserves that fact. It never enters the pending queue or accepts a fabricated
acknowledgement. Current operations may retain first archive provenance if selected again.

New event positions remain above every retained position. New snapshots and repeated preparation
retain historical facts and their delivery/provenance; last_committed_at includes historical receipts
and remains a timestamp summary, not ancestry proof. Historical setup cannot create a household or
grant founder provenance. Restored consumed/canceled recovery has a separate indexed guard: an old
approval cannot grant access under a new key, pending lists exclude it and target ownership precedes
closure disclosure. An authorized original-key retry may still return its historical result.

Before activation, remaining work must stop writes, prove the source binding is unchanged, apply
the verified import/migration to a blocked candidate, switch durably and recover interruption with
rollback data retained. Both deployment modes and the actual packaged SQLite still require restore
acceptance. The owner's installed Edge.2 remains on schema 3; it was not updated to this code.
No automatic snapshot frequency or retention is selected. See
[runtime history evidence](evidence/m1-runtime-history.json).

Managed startup now also understands an explicit format-2 root generation selection while retaining
flat format-1 compatibility. Each selected slot has bound identity and a marker that blocks direct
slot startup; root leases still apply. Both composed APIs and snapshot/preparation fixtures exercise
that layout. No production command publishes a new selection yet. This is a prerequisite for the
future atomic switch, not completed activation. See [data layout](owned-data-directory.md) and
[generation evidence](evidence/m1-generation-selection.json).

See the [complete restoration SDD](../specs/platform-restoration.md),
[source-identified preparation evidence](evidence/m1-restoration-planning.json),
[manual snapshots](snapshots.md) and [architecture](architecture-identity-storage.md).
