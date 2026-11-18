# Daily automation schedule preview qualification

[Domus #124](https://github.com/vypdev/domus/issues/124) previews the next five
daily instants for a single household-local time. The
[automation specification](../../specs/household-automation.md) defines the
`daily-trigger-preview` requirements.

| Case | Verification |
| --- | --- |
| `daily-trigger-preview-C01` | The protected API tests freeze the clock before, exactly at and after the requested local time. Both HTTP compositions return the same five strictly future instants. Calendar bounds and a whole skipped local date keep enumeration finite and avoid duplicate instants. |
| `daily-trigger-preview-C02` | Europe/Madrid moves the requested 02:30 spring time to 03:00, the first valid local time, and returns the corresponding UTC instant. The panel shows both local times and the adjustment. |
| `daily-trigger-preview-C03` | Both household policies resolve Europe/Madrid's repeated autumn 02:30. The exact instants differ by one hour, and the panel labels both outcomes. |
| `daily-trigger-preview-C04` | Foreign or missing session context and revoked automation access produce the protected failure states. The authorized read leaves draft, task, stock, audit and receipt storage unchanged. |
| `daily-trigger-preview-C05` | The compiled workspace journey covers invalid English input, keyboard submission, a failed read in Spanish on a narrow touch viewport, and retry with the retained input. Browser state tests retire results when the household or current authorization changes. |
| `daily-trigger-preview-C06` | The contributing pull request records the exact source, amd64 and aarch64 CI jobs, deployment results and separately installed Edge acceptance with cleanup. |

The [protected API tests](../../tests/backend/test_automation_schedule_preview.py)
exercise the shared application read in both HTTP compositions. The
[preview unit tests](../../frontend/tests/automation-schedule-preview.test.ts)
cover the transport, scoped controller and shared controls. The
[compiled browser journey](../../frontend/tests/e2e/workspace-navigation.spec.ts)
uses the protected endpoint from the Household page.

`GET /api/v1/automation/schedule-preview?time=HH:mm` uses the verified household
context in [Ingress](../contracts/native-household-api.openapi.json) and
[standalone](../contracts/household-api.openapi.json). The read uses the
existing time policy and SQLite schema 33.
