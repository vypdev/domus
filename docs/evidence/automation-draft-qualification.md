# Automation draft qualification

[Domus #118](https://github.com/vypdev/domus/issues/118) adds inactive drafts to
the [manual automation preview](automation-preview-qualification.md). The
[automation specification](../../specs/household-automation.md) owns the
requirements `automation-drafts-R01` through `automation-drafts-R04`.

| Case | Verification |
| --- | --- |
| `automation-drafts-C01` | The native and standalone HTTP tests save, list and reopen the exact version-one task proposal and condition, including the maximum condition depth. |
| `automation-drafts-C02` | The HTTP tests exercise current membership and task grants, scoped references and validation that preserves the last saved revision. |
| `automation-drafts-C03` | The HTTP tests exercise concurrent writers, immutable revision history, identical replay and conflicting key reuse. |
| `automation-drafts-C04` | The HTTP tests compare task and inventory data and the pending outbox before and after save and preview. The save records an audit envelope acknowledged in its own transaction for receipt restoration. |
| `automation-drafts-C05` | The [compiled browser journeys](../../frontend/tests/e2e/workspace-navigation.spec.ts) cover English desktop keyboard and Spanish narrow touch, with screenshots in both themes. They reopen a saved stock condition after reload, lose a committed response and recover its receipt, then compare the competing revision and save the preserved input. A delayed open and a failed, then delayed, initial list keep the editor locked until the saved definition or pending request is known. |
| `automation-drafts-C06` | The SQLite tests exercise byte-identical migration rollback, restart, checkpoint restoration and rollback for the [schema 20 fixture](../../tests/fixtures/sqlite/v20-inventory-history-source.sql) and [schema 31 fixture](../../tests/fixtures/sqlite/v31-automation-drafts-source.sql). Edge.32 at `43bace9576b9468f789fe9975a3dd5fe427d83ae` produced the schema 31 fixture with a named purchase session and its original receipt. |
| `automation-drafts-C07` | The compiled browser journeys run through Ingress and standalone. The contributing pull request records the image and installed Edge qualification and cleanup. |
