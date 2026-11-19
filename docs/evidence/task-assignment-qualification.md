# Task assignment interface qualification

[Issue #141](https://github.com/vypdev/domus/issues/141) connects the protected
assignment command to the Tasks workspace. The owning companion is
[task assignment interface](../../specs/task-assignment-interface.md), alongside
the retained household task and execution contracts.

The editor follows the selected task's current `assign` action. It reuses the
authorized household roster, published ha-ui checkboxes and task request journal.
Current command authorization and expected revision govern every save. Provider
name availability and active household membership have separate meanings. A
missing provider name retains the canonical household identity as its label.
The existing public `task_assignee_denied` code preserves an authorized editor's
selection for correction. A current permission denial retires its protected view.

The real lost-response journey exposed a recovery gap. The existing workspace
original-request allowlist omitted `task.assign`, returning HTTP 422 after an
assignment had committed. Both the typed route and application query now admit
the assignment action through their existing recorded-authorization boundary.
The two published OpenAPI projections include that action. A recovered receipt
binds the occurrence, revision and assignee set to the frozen request.

| Published case | Executable evidence |
| --- | --- |
| task-assignment-interface-C01 | The [compiled assignment journey](../../frontend/tests/e2e/tasks.spec.ts) selects two named active members and checks the stored canonical identities and current projection. The [component cases](../../frontend/tests/task-component.test.ts) cover controlled ha-ui selection and deliberate save. |
| task-assignment-interface-C02 | The compiled journey replaces the set and releases work. The component tests enforce the in-progress minimum. The retained [command](../../tests/backend/test_task_commands.py) and [state policy tests](../../tests/backend/test_task_policy.py) exercise the authoritative state constraints. |
| task-assignment-interface-C03 | The [HTTP recovery regression](../../tests/backend/test_task_http.py) covers both compositions and current role revocation. The [query tests](../../tests/backend/test_task_queries.py) cover own-operation scope, explicit management exceptions and their revocation. Existing protected command tests reject restricted reassignment and unavailable household identities. |
| task-assignment-interface-C04 | The component tests distinguish pending discovery, successful empty discovery, denied access and unavailable reads, retain the draft, and expose refresh and removal of stale selections. Provider-name denial preserves canonical eligible options. |
| task-assignment-interface-C05 | Two authenticated browser tabs compete at the current revision. The losing editor retains its chosen member, shows the changed assignment and requires explicit review before a fresh save. The [controller tests](../../frontend/tests/task-controller.test.ts) also cover a conflict arriving after preflight and failed current reads. |
| task-assignment-interface-C06 | The compiled journey commits a release and drops its response. Reload and protected original-request recovery preserve the key, body and operation without another write. [HTTP decoding](../../frontend/tests/task-http.test.ts) refuses a receipt with a different assignee set. [Journal tests](../../frontend/tests/task-journal.test.ts) preserve assignment and older creation records together across reload. |
| task-assignment-interface-C07 | The [domain cases](../../frontend/tests/tasks.test.ts) admit empty release and one through 32 unique IDs, while refusing duplicates, malformed IDs and a 33rd selection. The normal composition decoder preserves those bounds. Backend assignment tests reject foreign, inactive and unsupported identities. |
| task-assignment-interface-C08 | Four compiled journeys exercise Ingress and standalone with English desktop keyboard and Spanish 390 px native touch. They cover editing, cancellation, multiple selection, save, conflict review and original-request recovery. Focus regressions cover the first choice, cancelled editor, failed validation and current-assignment review. |
| task-assignment-interface-C09 | Those journeys restart the actual composed runtime and recover the unchanged assignment operation, complete work under the actual performer, then restore the earlier checkpoint. An exact original PUT returns its historical result while the restored assignment and audit counts remain unchanged. [Restoration](../../tests/backend/test_task_restoration.py) and [history tests](../../tests/backend/test_sqlite_task_history.py) exercise durable original receipts and inspectable assignment history. |

The interface and recovery allowlist use storage schema 34 and the existing
assignment, receipt and restoration formats. The selected ha-ui version is
`0.1.0-next.2`.

Current-source Chromium qualification passes all four new compiled journeys.
The full frontend suite passes 1,833 cases with 100% of all four supported metrics
globally and per authored runtime file. The backend passes 5,513 cases with 100%
statement and branch coverage globally and across all 231 modules, independently
audited per file. Architecture-specific CI and final review are tracked in
[PR #142](https://github.com/vypdev/domus/pull/142).

## Immutable candidate

Edge.48 uses runtime source `95fff8ab5ff0a5a85872596447c314e365813d1b`.
Its source archive SHA-256 is
`c1b43ec66442834ca7f2093660ab6700ddc18dd31496ef982c0df564305faa5f`.
The measured Linux wheel SHA-256 is
`498b3840ca22370da8a77822027d3332240e9c0d4e5827dcad8b7e122b329bfb`.
All 231 Python modules match Git and the installed Linux builder. Its four
compiled UI files also match the independently built local bundle.
The [artifact declaration](../../addon-edge/artifact.json) records those exact bytes.

The ARM64 image is
`sha256:08f426df9f0bc9d0c3441eb0505b55a47fd0b507c5f3932d7e5952d94b296e9a`.
Nine actual-image cases passed, covering every declared Python/UI file, native
authority and restart, private standalone delivery, an actual Edge.5 upgrade and
restore, repeated SIGTERM cleanup, and all four real-Core deployment compositions.
The four assignment browser journeys also passed against this exact installed
image in Ingress and standalone, with English keyboard and Spanish native touch.

The first CI campaign exposed a browser-test bootstrap race after standalone
restart. The test selected Spanish while authentication was still loading, then
waited for Spanish navigation after the completed bootstrap selected English.
The journey now waits for authenticated navigation before changing language.
All four actual-image assignment journeys passed three consecutive repetitions.

## Installed Home Assistant acceptance

Chrome verified installed version `0.0.0-edge.48` using the Action-managed issue
branch and the synthetic household `Domus QA 141 Edge48`. English keyboard input
assigned a task, retained an empty draft across two competing updates, focused
explicit current-assignment review and deliberately released the task. The
390 px Spanish touch journey assigned, cancelled an edit, released and reassigned
another task. Dark-theme text, focus and the assignment controls were legible.

The app stopped with Home Assistant's `Detenido` state and restarted successfully.
Both task identities persisted. The released desktop task retained revision 5
and the assigned mobile task retained revision 4. Checking the saved assignment
after restart recovered its recorded operation. The isolated-image SIGTERM cases
also require a zero exit status.
