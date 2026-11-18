# Inactive daily automation drafts qualification

[Domus #126](https://github.com/vypdev/domus/issues/126) adds the Daily
trigger to immutable automation drafts in Household. The
[automation specification](../../specs/household-automation.md) defines
the `daily-drafts` requirements and acceptance cases.

| Case | Verification |
| --- | --- |
| `daily-drafts-C01` | The protected draft command and rule codec accept version-one manual definitions and version-two daily definitions. Both reject unsupported trigger fields, mismatched versions and invalid minute times. |
| `daily-drafts-C02` | A repeated request and original receipt lookup return the same committed revision. The compiled journey drops the committed response, reloads and recovers the same save and time. |
| `daily-drafts-C03` | Two protected writers race from the same expected revision. One wins. A simulated receipt write failure rolls back its draft revision so the original request can be retried. |
| `daily-drafts-C04` | Foreign context and suspended membership cannot read or write a draft. Existing protected grants still apply to every read, command and receipt. |
| `daily-drafts-C05` | Manual configuration rejects any daily revision. A previously enabled manual revision can still run and show its original receipt and history. A corrupted daily control also fails before task creation. |
| `daily-drafts-C06` | The compiled workspace journey chooses Daily by English keyboard, recovers a committed save and opens the stored time by narrow Spanish touch. Frontend tests check invalid time, both trigger labels, conflict review, and original local recovery bytes. |
| `daily-drafts-C07` | Representative schema 33 and 20 data migrate to schema 34. The legacy manual draft, control and original receipt survive migration. A new daily definition survives restart; restoring an earlier revision preserves the later historical receipt without applying it. The previous schema boundary rejects the upgraded database before modifying it. |
| `daily-drafts-C08` | The contributing pull request records exact-head amd64 and aarch64 CI, both protected deployments and separately installed Edge acceptance with scoped cleanup. |

The [backend tests](../../tests/backend/test_daily_automation_drafts.py),
[frontend draft tests](../../frontend/tests/automation-drafts.test.ts)
and [compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts)
cover the saved definition and its recovery.

The current version discriminator is part of the existing draft save and
read in [Ingress](../contracts/native-household-api.openapi.json) and
[standalone](../contracts/household-api.openapi.json). The draft table
keeps its existing immutable envelope. SQLite schema 34 marks the
compatibility boundary for readers of the version-two definition.
