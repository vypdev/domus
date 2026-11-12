# Manual automation preview qualification

[Issue #98](https://github.com/vypdev/domus/issues/98) adds a protected read-only preview
for a manual rule in Household settings. The versioned rule has one task proposal
and can evaluate an optional stock condition against the current household snapshot.

| Published case | Executable evidence |
| --- | --- |
| `automation-preview-C01` | The [independent HTTP cases](../../tests/backend/test_automation_preview.py) run in both compositions. C01 repeats a deterministic manual proposal at the title limit and without a stock condition. |
| `automation-preview-C02` | C02 verifies typed all, any and not, a maximum condition depth of eight, a 64-node rule limit and closed request fields. |
| `automation-preview-C03` | C03 reads available stock before and after it reaches the configured minimum. A reservation brings available stock below the minimum again. The case checks the condition trace and no-action result. |
| `automation-preview-C04` | C04 rejects forged context, invalid CSRF or Origin, revoked task grants and references unavailable in the household. It compares snapshots of tasks, stock, receipts, audit and outbox. |
| `automation-preview-C05` | The [controller and transport tests](../../frontend/tests/automation-preview.test.ts) allow a title-only preview when the first catalog load fails, preserve the draft on retries, check response identity and retire obsolete results on navigation or account change. The [workspace composition test](../../frontend/tests/page.test.ts) also clears the draft on a member replacement. |
| `automation-preview-C06` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) rejects 161 code points without clearing the draft and previews 160 supplementary characters with English desktop keyboard input even during a catalog outage. Retrying the catalog preserves the title and clears the old result. The journey also retries a preview read, checks the product list after returning from Inventory, previews matching and nonmatching conditions with narrow Spanish touch input and compares the task definitions before and after. |
| `automation-preview-C07` | The Edge package tests verify the pinned source and compiled assets. Image CI runs the workspace journey in both compositions on amd64 and ARM64. See [installed Edge.29](#installed-edge29) for the Supervisor walkthrough. |

The [native contract](../contracts/native-household-api.openapi.json) and the
[standalone contract](../contracts/household-api.openapi.json) publish the same
preview request and result shapes. Preview uses the existing storage schema.

## Installed Edge.29

On 2026-11-12, Supervisor reported `0.0.0-edge.29` for the temporary
`904f4e29_domus_edge` application. The [artifact declaration](../../addon-edge/artifact.json)
pins runtime `23f90008f5bb1f98bae40a1b54acf75b061ec2fc`, built for aarch64
with SQLite schema 31. An empty, disposable Europe/Madrid household verified:

- English keyboard preview returned focus to an empty title and then proposed the corrected title.
- Returning from Inventory preserved the title and loaded a newly registered product.
- Spanish touch at 390 × 844 proposed the task when stock was below the minimum.
  After a separate intake brought stock to the minimum of two, the same preview
  said no task would be created. Tasks remained empty, available stock stayed at
  two, and Family displayed its zero balances.

The temporary app, its private data and its repository source were removed.
Supervisor returned to the original 14 installed apps and eight sources.
