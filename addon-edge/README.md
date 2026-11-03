# Domus Edge

Development preview of Domus installed as a Home Assistant app. Open it through HA's Open Web UI;
it uses your existing HA sign-in without another login.

Edge 0.0.0-edge.7 includes the English/Spanish household administration workspace: participant roster,
household settings, HA administrator mapping, member roles/ordinary permissions, public aliases
and owner-private preferences. Reviewed changes retain exact revisions and original operation
identity; a changed verified household retires private drafts. Saved preferences describe stored
choices; notification delivery remains unavailable.

Edge.7 also requests cold Supervisor backups: HA stops the app while copying its private data.
The brief interruption closes in-memory sessions; reopening verifies the current HA identity.

This version upgrades verified older data to SQLite schema 9. Preserve the original application/data
checkpoint and use the documented compatible restore/rollback procedure. Existing identity,
household records, history and original-operation evidence are retained. The installed Edge.5
recipe is preserved separately as an immutable compatibility fixture.

Set your Home Assistant browser origins in Configuration before starting. Edge remains experimental;
the remaining domain screens, required human UX/owner adoption and complete Stable product are
still in progress.

See [installation and permissions](DOCS.md) and the [reviewed artifact declaration](artifact.json).
