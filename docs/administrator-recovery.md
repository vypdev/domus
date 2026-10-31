# Administrator access recovery

Status: the target-bound recovery model, SQLite schema 3, human routes in both native/standalone
compositions and installation-console command are implemented. Tests include actual ASGI/SQLite
journeys and a separate process using a real terminal. Edge.2 packages these services; the owner has
verified its connection page and restart, without exercising live recovery. Edge.3 adds retained
closure guards and real-image restoration tests. Full live recovery acceptance remains pending.

## Recover access

A current active human HA administrator can request recovery in setup_administrator or
selected_ha_user mode. The target always comes from that person's server-proven session. Opening
Domus or knowing a request ID cannot create a grant. The all_ha_administrators mode uses its ordinary
current-source enrollment path and does not enable this recovery flow.

1. Sign in through HA and POST /api/v1/recovery/requests with `{"expected_revision":0}`, a new
   Idempotency-Key, exact configured Origin and the own session's X-CSRF-Token. Keep the returned
   request ID and original operation ID. Retrying the same body/key returns the original result.
2. An installation operator reviews that exact request from the local host/container console:

   ```sh
   domus-admin --channel edge --data-directory /data/domus \
     recovery approve <request-id>
   ```

   The process must run as the runtime UID that owns the data. For an independently configured
   standalone file, use the matching explicit installation configuration instead:

   ```sh
   domus-admin --channel edge --database /owned/data/domus.sqlite3 \
     --instance-id <persisted-installation-uuid> recovery approve <request-id>
   ```

3. The terminal displays installation UUID/channel, exact HA target, mapping and policy revision,
   existing member linkage/revision/profile/status, pending-request expiry and the intended explicit
   administrator/active grant. Both input and output must be terminals for a new approval. Type the
   displayed `APPROVE <request-id> <target-ha-user-id>` line exactly. This is local confirmation, not
   a shared password/PIN or a secret that a browser can submit. There is no --yes bypass.
4. The same human POSTs /api/v1/recovery/requests/<request-id>/complete with
   `{"expected_revision":2}`, current session CSRF/Origin and its own Idempotency-Key. Fresh exact HA
   administrator proof is required again. A changed mapping/policy revision or member linkage/revision
   invalidates the prepared approval. HA unavailability blocks completion.
5. Completion grants an independent explicit administrator profile and active membership, preserving
   existing member ID, HA linkage and permission exceptions. A previously pending/suspended/archived
   target is explicitly reactivated only through this reviewed recovery. The configured mapping is
   retained. Consumption, member change, receipt, audit and outbox commit together. Event delivery
   remains separate from that durable result.

A pending request expires ten minutes after creation. Confirming that live request creates one
approval valid for ten full minutes from confirmation. Replaying approval retains its original fixed
deadline. Only one live
request per target is admitted, with a bounded household inventory. Expired/canceled/consumed approvals
cannot grant another effect. Concurrent completion has one result; identical same-key retry recovers
it, while another key cannot consume the approval again. A committed completion's original result is
available only under current Domus administrator authority; suspension or permission loss blocks it.

GET /api/v1/recovery/requests/<request-id> returns only the requesting human's own state and binding
summary. Unknown or another person's request is unavailable. Existing local read-grace sessions may
view that status until their original session deadline during a bounded HA outage. They cannot write.
The owner may POST .../<request-id>/cancel using the current request revision (1 pending, 2 approved)
and the same write protections. Cancellation grants no privilege and also works for an otherwise
eligible HA human who has lost HA administrator status.

## Console and data boundaries

Approval is a console-only application port; neither HTTP deployment composition exposes it. The CLI
uses existing ready data, never generates installation identity and never creates or migrates a
schema. It needs no HA transport token. A native console attachment holds a shared maintenance guard
while the runtime retains its exclusive process lease. Startup migrations require exclusive
maintenance access. The explicit-file CLI rejects an owned-directory marker, requiring --data-directory
instead of bypassing that protocol. All normal SQLite writer/revision guards still apply.

A canceled/interrupted terminal does not approve. If output fails after commit, the CLI reports that
it could not confirm the result and instructs inspection or retry of the same request; it does not
claim no effect. Repeating approval for an already approved live request returns the same receipt.
Existing business and replay records are retained on rejected or uncertain commands.

See [source-identified evidence](evidence/m1-administrator-recovery.json),
[migration behavior](migrations-identity-storage.md), [owned data](owned-data-directory.md),
[HTTP contracts](household-api.md) and [remaining operational work](operations-identity-storage.md).
Consistent snapshot/restore, packaged directory provisioning and owner HA recovery acceptance are
still pending. No automatic backup frequency or retention is introduced.
