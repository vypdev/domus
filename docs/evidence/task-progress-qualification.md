# Task progress interface qualification

Issue #143 connects the existing task transition command to the Tasks workspace.
The owning companion is [task progress interface](../../specs/task-progress-interface.md).
The retained household task, execution, category and assignment owners keep their
published case identities and behavior.

Start confirms the assigned-to-in-progress transition. Block confirms a meaningful
multiline reason. Unblock confirms Assigned when assignees remain and Available
when the assignee set is empty. Current server hints determine discovery. The
command transaction enforces current target-specific grants, household scope and
the exact reviewed revision. Assignee identities remain unchanged.

The editor uses released ha-ui buttons, cards and feedback from `0.1.0-next.2`.
It preserves the existing multiline text validator and 1,000-code-point bound.
A competing update retains the proposed target and reason. A separate review
accepts current facts before a deliberate save. An unavailable target offers
refresh and cancellation. Opening progress confirmation preserves other task
form drafts and hides their competing actions until the confirmation closes.

The existing workspace original-request allowlist now includes `task.transition`
through recorded authorization. Both OpenAPI projections include the action.
Original receipt decoding binds the task, revision, target and exact reason to
the frozen journal request. Existing creation and assignment entries remain
readable. Storage schema 34 and the persisted transition format are retained.

| Published case | Executable evidence |
| --- | --- |
| task-progress-interface-C01 | The [compiled progress journeys](../../frontend/tests/e2e/tasks.spec.ts) start assigned work, block it and unblock it while checking revisions and assignees. The [component tests](../../frontend/tests/task-component.test.ts) require confirmation before each command. |
| task-progress-interface-C02 | The compiled journeys block available work, return it to available and verify an empty assignee set. The retained [execution command tests](../../tests/backend/test_task_execution_commands.py) cover current target-specific grants. |
| task-progress-interface-C03 | The [HTTP recovery regression](../../tests/backend/test_task_http.py) exercises both compositions and denies original disclosure after role revocation. The retained [query tests](../../tests/backend/test_task_queries.py) verify recorded authority, scope and transition target. |
| task-progress-interface-C04 | The [domain tests](../../frontend/tests/tasks.test.ts), component tests and [normal page decoder tests](../../frontend/tests/page.test.ts) reject blank, invalid Unicode, controls and over-bound reasons. The compiled journey checks correction and exact saved multiline text. The retained backend validators enforce the same bound. |
| task-progress-interface-C05 | Two browser tabs compete at one revision. The losing editor retains its reason. A still-permitted target requires explicit current review and a separate save. An unavailable target requires refresh or cancellation. The [controller tests](../../frontend/tests/task-controller.test.ts) include a conflict after preflight. |
| task-progress-interface-C06 | The compiled journey commits a transition and drops its response. Reload recovers the same original operation. Exact replay preserves counts and changed key payload conflicts. [Transport tests](../../frontend/tests/task-http.test.ts) reject mismatched receipts. [Journal tests](../../frontend/tests/task-journal.test.ts) retain progress alongside older entries. |
| task-progress-interface-C07 | Four execution command tests inject failure after an actual occurrence write, verify rollback of state and evidence, and retry the same original key successfully. Controller and component tests preserve correctable input across unavailable, denied and uncertain outcomes. |
| task-progress-interface-C08 | Four compiled journeys cover Ingress and standalone with English desktop keyboard and Spanish 390 px native touch. Component tests assert reason, review, cancellation and recovery focus, public ha-ui controls and inert text. |
| task-progress-interface-C09 | The compiled journey restarts the composed runtime, checks its saved reason and original operation, completes work, then restores an earlier checkpoint. Original replay returns the historical operation and leaves the restored current task and evidence counts unchanged. |

The local frontend campaign passes 1,912 tests with all four coverage metrics at
100% globally and per authored runtime file. The independent specification SDK
accepts all nine supplied cases, reciprocal requirements and retained owners.
The complete backend campaign passes 5,515 tests with 100% statement and branch
coverage globally and per authored module, followed by an independent source
audit. Four subsequently added late-write rollback cases and ten normal-HTTP
Unicode-bound cases pass separately. Final CI collects their combined inventory.

All four compiled progress journeys pass. They check readable card text and
primary actions in both themes. An observed dark-theme primary-button ratio of
1.72 failed the regression before the public on-accent token was supplied by the
Tasks host. The same host tokens also reach the nested policy controls. The
tests wait for the theme transition's final contrast before measuring it.

The longer journey uses the existing Saved requests interface to dismiss a
resolved creation request before reaching the fixed eight-record journal
capacity. It retains the original transition receipt for restart and restoration.
The complete source campaign passes all 119 compiled browser journeys without
skips, unexpected results or flaky outcomes. The rebuilt catalog passes all
45 journeys. The CPU image campaigns and immutable installed-owner acceptance
are tracked in [PR #144](https://github.com/vypdev/domus/pull/144).

## Immutable candidate

Edge.50 packages runtime source `cec2d43e79cea9f45f4586354d97c5a1ac847570`.
The source archive SHA-256 is
`a98f912b04586488cc4e116892db60efb7848a7cc15536fd585f514386502aab`.
The independently measured Linux wheel SHA-256 is
`a6df90b4b5704b02db20537d0b76b8cb4ed25875167e1293a8a96ea771b4d49b`.
All 231 Python modules match Git, the wheel and the installed Linux builder.
The four compiled UI files match the local and Linux builds. The
[artifact declaration](../../addon-edge/artifact.json) records those exact bytes.
The ARM64 image is
`sha256:746bb6b63641f07ce436cd66c16bffa89ddf887244856dfd5c176b201e9a502b`.
Nine actual-image cases pass, covering all declared bytes, native authority and
restart, standalone delivery, an actual Edge.5 upgrade and restore, repeated
SIGTERM cleanup and all four real-Core deployment compositions. Eight task
browser journeys pass against this exact image, covering assignment and progress
in Ingress and standalone with English keyboard and Spanish narrow native touch.
Installed-owner acceptance and final same-head CI and review are recorded in
[PR #144](https://github.com/vypdev/domus/pull/144).

The first package-head CI caught a stale current-bundle fingerprint in the
navigation evidence manifest. The normal wheel acceptance reproduced the
failure. Its current-file declaration now matches the independently measured
Edge.50 bundle, and the unchanged wheel/asset/license acceptance passes. The
immutable runtime source, archive, wheel and image retain their measured bytes.
