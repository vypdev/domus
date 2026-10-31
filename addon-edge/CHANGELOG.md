# Changelog

## 0.0.0-edge.3

- Preserve complete original operation history separately from restored household state in SQLite schema 4.
- Add console-only restore preparation, verification, activation, status and interruption recovery.
- Retain a verified pre-activation source checkpoint; rollback also preserves newer replay evidence.
- Migrate only a verified target during restoration and retain original source data.
- Prevent reusing consumed or canceled recovery approval after restoring an older checkpoint.
- Mark the schema/history boundary as breaking: an older image must not open schema 4 or selected generations.
- Keep the complete product UI, live restore and production acceptance pending.

## 0.0.0-edge.2

- Add private persistent installation identity and SQLite household/member/policy/recovery services.
- Prepare only the app's own private data child, then run the server without root privileges.
- Require one to four fixed Home Assistant browser origins in the app configuration.
- Preserve data and original-operation receipts on restart; keep sessions in memory.
- Include manual snapshot creation/inspection and console-only recovery approval; restore remains pending.
- Keep the full household UI and production acceptance pending.

## 0.0.0-edge.1

- Add the native Home Assistant authentication preview without an additional sign-in.
- Bind the locally built app to reviewed runtime source and locked dependencies.
- Keep household commands, product UI and production acceptance explicitly pending.
