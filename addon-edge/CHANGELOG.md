# Changelog

## 0.0.0-edge.5

- Translate the technical membership status in both English and Spanish.
- Preserve the setup draft while switching languages with technical details expanded.
- Verify original receipts survive actual browser-tab closure without automatic duplicate work.
- Keep SQLite schema 7 and the existing identity, private listener and Core API permission scope.
- Pin the corrected reviewed source and its verified archive checksum as a distinct immutable build.

## 0.0.0-edge.4

- Add the English/Spanish household entry UI through the existing Ingress session and private listener.
- Require explicit household setup and own membership; retain exact original requests for deliberate recovery.
- Preserve in-flight command evidence when a stale close intent arrives; normal close resumes after completion.
- Build the exact reviewed UI with immutable Node/source inputs and include it in the installed Python wheel.
- Keep Node, browser fixtures and development dependencies out of the runtime image.
- Upgrade verified older data to SQLite schema 7, retaining identity, household records, history and replay guards.
- Mark the schema boundary as breaking; require explicit upgrade and reject old-image downgrade without changing data.
- Keep other domain screens, stable release and complete product acceptance pending.

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
