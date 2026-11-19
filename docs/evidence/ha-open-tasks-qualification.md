# Home Assistant open-task list qualification

[Domus #137](https://github.com/vypdev/domus/issues/137) implements the
[open household task companion specification](../../specs/home-assistant-todo-list.md).
The [task list guide](../tasks/ha-open-tasks.md) describes the grant, connection,
read-only behavior and recovery in English and Spanish.

| Case | Verification |
| --- | --- |
| ha-open-tasks-C01 | Real SQLite fixtures on Ingress and standalone compare every open state with the authoritative occurrence records. They exclude completed, cancelled and skipped work, distinguish same-title occurrences, and retain identity across state changes and reopening. Definition edits preserve existing occurrence snapshot titles. Core verifies stable UIDs when a response title changes. |
| ha-open-tasks-C02 | A snapshot returns exactly 1,000 open occurrences through 101-record queries using one SQLite read connection. This crosses the first 25 and the 101/102 boundary. The 1,001st occurrence returns unavailable with zero partial items. Core accepts 1,000 and rejects 1,001. |
| ha-open-tasks-C03 | Both protected routes verify default-disabled, missing, rotated, foreign, cross-channel and wrong-purpose grants. Calendar, deadlines, low-stock and shopping projections retain independent credentials. |
| ha-open-tasks-C04 | Only title, state and opaque UID are published. Repeated successful and failed reads preserve persisted facts. A task bearer cannot authorize the ordinary task write route. Core exposes zero mutation features and rejects native add, complete and delete operations. |
| ha-open-tasks-C05 | Disposable Core verifies English and Spanish state labels, entity names, stable source and occurrence identities, bearer rotation, separate sources and a fresh process restart with the saved entries. |
| ha-open-tasks-C06 | Core distinguishes empty, malformed, denied and recovered reads. It rejects duplicate JSON keys, unexpected fields, invalid titles, states and UIDs, duplicate occurrences, oversized and invalid UTF-8 bodies. Failed reads hide cached items and clear the item subscription. Unload stops scheduled refreshes. |
| ha-open-tasks-C07 | The packaged acceptance connects disposable Core to isolated Supervisor and HTTPS standalone compositions for both Edge and Stable fixture data. Image architecture and separately installed Edge acceptance are recorded with the final candidate. |

The [artifact declaration](../../addon-edge/artifact.json) identifies the exact
Edge runtime, source archive, wheel and installed files. The projection uses
SQLite schema 34.

Local disposable Core `2026.10.4` passed with all ten authored Python modules
at 100% statement and branch coverage, covering 581 statements and 136 branches.

The local backend campaign covered all 230 modules at 100%, including 17,865
statements and 4,832 branches. The frontend passed 1,786 tests with 100% statements,
branches, functions and lines. The compiled local Ingress and standalone journeys
passed all 111 browser cases.

The preparatory SDD CI run `44407258836` encountered an ARM64 browser-port collision
with a local browser campaign on the shared host. That local campaign has finished.
Further local entry-browser campaigns use the workflow's existing shared
`/tmp/domus-ci-entry-browser.lock`. Final candidate CI verifies both architectures.

The installed Edge.45 English keyboard journey created, claimed and completed an
identifiable synthetic task. Its dark-mode capture exposed a white allocation
card with light text. The shared Domus theme now supplies the published card's
raised-surface token. The existing compiled Ingress and standalone journeys verify
dark backgrounds and readable text on both household and task allocation cards.
Both journeys passed after reproducing the original white background. The
corrected candidate uses a new immutable Edge version before installed acceptance.

A preparatory ARM64 browser run received the bounded `storage_busy` response while
seeding inventory data. The fixture now verifies `Retry-After`, retries the exact
key and payload once, and retains the final success assertion. A deliberately
held SQLite writer exercises that path, followed by an identical replay that
returns the original result. Both protected journeys passed this regression.

The preparatory amd64 run `44423343964` crossed UTC midnight between fixture
seeding and the live Core deadline assertion. The original next-day deadline
correctly became due today. The fixture now schedules its future deadline and
recurrence two days ahead, within the same three-day calendar acceptance window.
A controlled SQLite reproduction seeded at 23:59 UTC confirms that the original
fixture changes from zero to one due-today item at 00:01, while the corrected
fixture keeps zero due-today and one overdue item across that boundary. The exact
Edge.46 packaged Core acceptance passed again after this fixture correction.

Home Assistant separately installed and ran Edge.46 with runtime source
`605eedbd688d35bbb6a69591e23a5d6b9a9acd84`. The synthetic household
`Domus QA 137 Edge46` passed task creation, claiming, completion and reasoned
reopening with English keyboard input and Spanish touch input at 390 by 844.
Titles containing angle brackets and ampersands rendered as text. Both reopened
tasks remained assigned after reloading. Captures confirm readable dark task
allocation cards in both languages. The owner installation exercised the app and
its optional task-digest configuration. Native entity grants and lifecycle were
verified in the disposable Core compositions described above.

Installed acceptance uses archive SHA-256
`96686291b73e93052814c97eee5c52e3dd713236b102d15f8a673bd1c07be145`
and wheel SHA-256
`b6d01600af38c6bfa71e48367cef2a52d05a3420c3e3b5351ac53371ee5b8b3c`.
The final PR records the temporary installation cleanup and final-head CI results.
