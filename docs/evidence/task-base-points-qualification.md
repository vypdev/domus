# Task base points qualification

[Issue #111](https://github.com/vypdev/domus/issues/111) lets task configurators set
the optional base amount during creation. The form uses the existing household default
when the amount is empty. The existing command boundaries store explicit amounts as
exact minor points and bind them to the original creation receipt.

| Published case | Executable evidence |
| --- | --- |
| `task-base-points-C01` | The [task form tests](../../frontend/tests/task-component.test.ts) exercise the optional control, blank inheritance and explicit zero. [HTTP tests](../../tests/backend/test_task_http.py) verify the current configuration grant and stored value. |
| `task-base-points-C02` | A basic creator retains title-only creation and the effective household default. A forged override and original recovery after role revocation are denied. The form offers to clear a retained amount after the configuration grant changes. |
| `task-base-points-C03` | Both HTTP compositions accept 0, 225 and 1,000,000 minor points and reject over-limit, negative, fractional minor units and coercible values. The [scheduled creation tests](../../tests/backend/test_schedule_creation_http.py) exercise the same amount in fixed and relative creation. |
| `task-base-points-C04` | The [command tests](../../tests/backend/test_task_commands.py) cover replay, concurrent matching requests, changed amount conflicts, rollback and restart. [Restoration tests](../../tests/backend/test_task_restoration.py) verify historical receipts and surviving definitions. The compiled browser journey recovers the original configured task after its response is lost. |
| `task-base-points-C05` | The [allocation tests](../../tests/backend/test_point_allocation_http.py) verify the same exact fractional base in the preview and the posted Points award. The compiled workspace journey exercises the existing Family ledger. |
| `task-base-points-C06` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) checks English desktop keyboard validation, Spanish narrow touch, the exact draft and the localized recovered amount. |

The increment uses the existing storage schema, award policies and restoration format.

Home Assistant Supervisor installed the disposable ARM64 Edge.24 candidate pinned to
runtime `f445f6e0ccffffb9a2fda43b029e1a3c6b908672`. The Ingress journey saved a task
with just a title. In English, pressing Enter with `2.251` displayed the validation
message and retained the draft and input focus. In Spanish at 390 px, the same draft
remained available. Touch submission with `2,25` saved the task and its receipt showed
exactly `2,25` base points. The disposable instance, synthetic data, and temporary
repository source were removed. The original 14 apps and eight sources remained.
