# Overview Family participation qualification

The protected summary shows completed tasks and posted earned points for the
verified member's current Family week. The backend derives the Monday boundary
from a server observation in the household time zone. [Issue #105](https://github.com/vypdev/domus/issues/105)

| Published case | Executable evidence |
| --- | --- |
| `overview-participation-C01` | The [Family Overview HTTP tests](../../tests/backend/test_family_overview.py) create real tasks and ledger awards. The summary matches the current Family report in Ingress and standalone. |
| `overview-participation-C02` | Sunday work approved and posted on Monday remains in the prior household week. A server observation on each side of local midnight verifies the boundary. |
| `overview-participation-C03` | A posted award from the next household week is excluded from the current read and appears in the next week. |
| `overview-participation-C04` | Work awaiting verification contributes to the completed count. Its expected points appear in Family's pending-verification value. |
| `overview-participation-C05` | Approved work awaiting ledger posting contributes to the completed count. Its expected points appear in Family's pending-posting value. |
| `overview-participation-C06` | The same HTTP tests switch verified members and confirm each receives their own totals. Forged context, caller-selected member and revoked Household or Tasks access return no participation facts. |

The [browser tests](../../frontend/tests/e2e/workspace-navigation.spec.ts) use
real posted points, recover a failed read and open Family from Overview using
English desktop keyboard and narrow Spanish touch in both compositions. CI
runs these journeys on amd64 and ARM64. The pull request records the exact
Edge package and installed acceptance.
