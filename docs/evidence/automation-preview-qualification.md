# Manual automation preview qualification

[Issue #98](https://github.com/vypdev/domus/issues/98) adds a protected read-only preview
for a manual rule in Household settings. The versioned rule has one task proposal
and can evaluate an optional stock condition against the current household snapshot.

| Published case | Executable evidence |
| --- | --- |
| `automation-preview-C01` | The [domain and HTTP tests](../../tests/backend/test_automation_preview.py) verify a deterministic manual proposal, the task title limit and a preview without a stock condition. |
| `automation-preview-C02` | The same cases verify typed all, any and not, a maximum condition depth of eight, a 64-node rule limit and closed request fields. |
| `automation-preview-C03` | Tests read available stock before and after it reaches the configured minimum and check the condition trace and no-action result. |
| `automation-preview-C04` | The two compositions reject forged context, invalid CSRF or Origin, revoked task grants and out-of-household references. A snapshot comparison checks tasks, stock, receipts, audit and outbox for effects. |
| `automation-preview-C05` | The [controller and transport tests](../../frontend/tests/automation-preview.test.ts) preserve the draft on failure, check response identity and retire obsolete results on navigation or account change. The [workspace composition test](../../frontend/tests/page.test.ts) also clears the draft on a member replacement. |
| `automation-preview-C06` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) corrects and retries a draft with English desktop keyboard input, then previews a matching and nonmatching condition with narrow Spanish touch input. It compares the task definitions before and after. |
| `automation-preview-C07` | The Edge package tests verify the pinned source and compiled assets. Image CI runs the workspace journey in both compositions on amd64 and ARM64. |

The [native contract](../contracts/native-household-api.openapi.json) and the
[standalone contract](../contracts/household-api.openapi.json) publish the same
preview request and result shapes. Preview uses the existing storage schema.
