# Validation evidence

Foundation audit on 2026-10-29, before tooling implementation. This historical record describes PR #3, not application acceptance. The issue #4 tooling increment and current delivery-quality SDD/catalog verification are recorded separately in [development evidence](evidence/development-tooling.json).

| Check | Result | Meaning |
|---|---|---|
| Original twenty-section headings | PASS — 11/11 | Exact comparison with the unchanged upstream template |
| Original draft format validator | PASS — 11/11 | Required headings, supported length and numeric budgets |
| Original consistency validator | PASS — 11/11 | Case IDs, per-area counts, reciprocal requirements and declared paths |
| Original prerequisite structure policy | PASS | Unchanged standard/template meet the required structure |
| Local document links | PASS | File links resolve; placeholders in the unchanged original template are excluded |
| Original SDK catalog validator | BLOCKED — 33 errors | Proposed capabilities have no implemented entrypoints, code or tests |
| Upstream policy provenance | PASS — 7/7 | Source-copy Git blob IDs match fetched upstream files |
| Copilot installation | Unchanged | No Copilot implementation, profile, workflow, template, guide or setup file was edited |
| Application tests / coverage | Not implemented | Planned acceptance cases are not executed tests |
| Real Chrome dogfooding | Not run | Requires an implemented identifiable artifact |
| Product readiness | Draft | Accepted owner choices are separate from outstanding engineering proof |

## Per-SDD results

| Capability | Requirements | Planned cases | Original format/consistency |
|---|---:|---:|---|
| platform-foundation | 6 | 20 | PASS |
| household-identity | 7 | 30 | PASS |
| household-tasks | 9 | 38 | PASS |
| recurrence-calendar | 8 | 37 | PASS |
| points-rewards | 6 | 44 | PASS |
| shopping-management | 7 | 21 | PASS |
| household-inventory | 8 | 35 | PASS |
| home-assistant-surface | 8 | 33 | PASS |
| application-experience | 6 | 26 | PASS |
| delivery-quality | 8 | 24 | PASS |
| household-automation | 9 | 45 | PASS |

Totals: 82 normative requirements and 353 distinct planned cases across eleven SDDs.
The owner-confirmed automation scope adds one engine capability with 45 planned cases; the HA surface remains the adapter owner.

## Catalog limitation

The unchanged SDK validator requires nonempty entrypoints, code and tests arrays even when status is proposed.
Eleven proposed capabilities therefore produce 33 precise absent-evidence errors; no other catalog errors were returned.
The original renderer generated CATALOG.md as an ownership view, not a validation override.
No fake implementation paths, status changes, schema substitution, weakened checks or Copilot edits were used.
Automatic feature-gate readiness remains blocked until real supported prerequisites exist.

## Reproduction and provenance

Copilot revision: f5e5a4cf9a80248994469cd88ad55eecab5b95ca.
Original validateSddMarkdown, validateSddDraftConsistency, validateSddPrerequisiteDocuments and validateCatalog
functions were run from byte-verified source copies. TypeScript was transpiled in memory without editing policy source.
Case/path consistency was checked against the actual PR base-tree inventory at 8ee7e1a15e91c91b6204ca97e8808c3207dee008.
All twenty headings were independently compared with the unchanged original template.

To reproduce, fetch the seven exact upstream files listed in the evidence JSON, verify Git blob hashes,
transpile TypeScript without changing policy, and invoke the named functions on the proposed documents and base inventory.
The standard and template are also unchanged copies. Tables, planned paths and acceptance counts are fully declared.
A local review runner cannot replace the Action's bundled authority.
[Raw results and source provenance](evidence/sdd-validation.json) include Git blob and SHA-256 hashes.

## PR #3 check audit — 2026-10-29

The reviewed head was fa7adf1118b85e1588f0de7d71a77f47822b5000. The initial Copilot - Commit attempt failed in automatic progress assessment with assessment-invalid, published as agent.failed. Its log did not identify an application-test or SDD-format failure. Retrying the failed job succeeded on attempt 2, including Copilot / Verification, without source/configuration changes to Copilot. [Inspect the run](https://github.com/vypdev/domus/actions/runs/40774284194).

Pull-request and branch-sync workflows passed for that head. Copilot / Review was neutral because draft review is disabled; it is not an approved-review result. A new documentation commit requires its own current-head checks and cannot inherit this audit as passing evidence.

## Subsequent check evidence and upstream ownership

A subsequent documentation head, ce2871b15508a1de53eaceca9bada001b31c25f2, failed progress assessment in both attempts with assessment-invalid exposed as agent.failed. The [second-attempt log](https://github.com/vypdev/domus/actions/runs/40787905127/job/123168549416) did not identify an application-test or SDD-format failure. Detailed sanitized evidence is recorded in [Copilot issue #774](https://github.com/vypdev/copilot/issues/774#issuecomment-6483788546); the separate deterministic proposed-catalog limitation is reported in [Copilot issue #777](https://github.com/vypdev/copilot/issues/777). No causal link between those two failures is asserted.

The current local document validation does not make either historical run green or claim current-head GitHub acceptance. New documentation commits have independent checks. Copilot and its installed resources remain unchanged while their owners investigate.

## Tooling increment after the foundation merge

Issue #4 registers real tooling/CI entrypoints, source and tests for delivery-quality only, while the capability remains proposed/Draft. The unchanged pinned SDK validator now reports 30 missing-evidence errors for the other ten capabilities. The earlier 33-error foundation result above is retained as historical evidence, not relabeled as passing. The updated owning SDD passes original format/consistency checks against its actual merged base at 0833f630aeff1b48558e0192e19ef3a42c328986. See [development](development.md) for executed tooling tests and remaining product acceptance.

## Reviewed bootstrap fix and M1 publication — 2026-10-31

Current reviewed Copilot v3 revision 3e7ceea08e6131360e026937d1c0cc1b120472e0 accepts
explicitly empty implementation arrays for proposed capabilities. The original current catalog validator
returns zero errors for Domus. The 33/30-error results above describe their exact older snapshots and
remain historical evidence.

The normal issue #6 workflow published the [companion](../specs/platform-foundation-identity-sqlite.md)
at commit 3fdf4f841e7e2f6d37f8ebfd4b8d80f1ce90090f, verified the exact remote branch and applied
branched. The original platform and identity owners were preserved. Current platform evidence describes
the partial storage, pure policy, local authorization, session-lease and HA protocol checkpoints.
Standalone authentication now has HTTP/CLI wiring and offline browser/session fixtures; complete
membership commands, business API, recovery and target acceptance remain pending.
See [storage evidence](evidence/m1-storage-kernel.json) and
[identity-policy evidence](evidence/m1-identity-policy.json) and
[standalone authentication evidence](evidence/m1-standalone-auth.json). Copilot and its installed resources remain
unchanged, and no manual branch exception was executed.

## Task-policy reconciliation — 2026-10-31

Issue #11 incorporates the owner-confirmed adult participation approval and scoped material defaults.
The four affected SDDs pass the unchanged format and consistency functions from byte-verified
Copilot revision 3e7ceea08e6131360e026937d1c0cc1b120472e0 against the develop base
e8fa5bbc9ffa179aa7559831f5f3d067c9c9c65c. Every original case row is retained; eleven new task
cases include explicit member denial and are not counted again in related capabilities.

The catalog now has thirteen Draft SDDs, 95 normative requirements and 443 distinct inventory IDs
across eleven capabilities. The historical 82/353 result above remains the PR #3 baseline, not a
current total. The unpublished household-interface proposal remains outside the catalog/count.
These documentation checks add no executed product journey or implementation evidence. The original
catalog validator and local links are separate from hosted current-head CI and complete Bugbot review.
[Policy review evidence](evidence/task-policy-sdd-review.json) records provenance, identities and counts.

## Task execution contract and first policy checkpoint — 2026-11-01

The Action registered the task-execution companion on its exact issue #13 branch at
`d4f3f911dd145d77255f47a882542f08e5c98055`. Original pinned format and consistency/path
validation passed against immutable base `a63b2315cd5121dde9585ba8875e286fdef5330e`.
Before runtime source changes, commit `48d8be0` published concrete planned module/test paths,
permission boundaries and the confirmed self-claim policy. Subsequent local refinements preserve
all 49 original household-task case rows and all 42 companion case rows.

The current inventory is fourteen Draft SDDs across eleven capabilities, 109 requirements and
485 distinct planned case IDs. The earlier thirteen/95/443 count describes the issue #11 snapshot.
The household-interface proposal remains unpublished and excluded from these totals.

The first executable task checkpoint is pure policy: 192 new tests, with all 153 statements and
58 branches covered. The whole backend passes 1,603 tests with all 4,857 statements and 1,366
branches covered. These are measured assertions and coverage, not 485 completed product journeys.
At that first checkpoint, task command authorization, SQLite records, HTTP and real consumer delivery
were unimplemented and prerequisite approval timing awaited the owner. A34 and the storage checkpoint
below supersede those two pending items. See [checkpoint evidence](evidence/task-execution-foundation.json).


## Task storage and confirmed prerequisite gate — 2026-11-01

The owner confirmed performed prerequisites as the household/task default, with an approved-work
alternative. The completion uses its saved rule snapshot; a caller cannot select a weaker gate.
This does not release points awaiting approval. The unchanged case inventory remains fourteen Draft
SDDs, 109 requirements and 485 planned IDs; all original 49 task and 42 companion rows are retained.

Schema 5 exposes typed task repositories through the existing unit of work. Actual file tests cover
compare-and-swap writes, immutable definition/cycle facts, scoped deferred cycle pointers, complete
checkpoint validation and migration/rollback from frozen schemas 1 through 4. Offline activation
restores old task state while retaining later completion receipts as processed; replay never
re-completes the task. Returning through the supported restore pipeline restores the sealed prior state.

The complete backend passes 1,867 tests, with all 5,326 statements and 1,520 branches covered.
The task modules contribute 613 statements and 210 branches; these are separate from claims about
task HTTP, live HA, UI, packaged adoption or real Inventory/Points consumers, which remain pending.
Strict types, the complete inward dependency graph, original pinned SDD/catalog validation and
local links remain required. Hosted current-head CI and a complete Bugbot review are independent gates.


## Current task authority checkpoint — 2026-11-01

Additive typed task permissions and application helpers now reread current membership, identity
mapping, profile/member rules and stored assignment/task defaults. Separate on-behalf authority
cannot remove a restricted actor's participation or invent another person's HA administrator proof.
Two negative tests demonstrate that stale assignment and weakened supplied snapshots cannot grant
access. Both actual composed OpenAPI contracts match the updated published permission enum.

The complete backend passes 1,910 tests with all 5,399 statements and 1,546 branches covered across
77 authored files. Nine task modules account for 681 statements and 236 branches; the focused identity
and task-authority suite passes 151 tests. The complete dependency graph keeps all three contracts;
strict types, formatting, 113 tooling/architecture fixtures and local links pass. Original pinned
format/consistency checks preserve the 49 task, 30 identity and 42 companion case rows, with the
same fourteen/109/485 planned inventory. These helpers still need transactional command/replay,
capacity/race and public task HTTP integration; no downstream or installed acceptance is implied.


## Durable task command checkpoint — 2026-11-01

The next source checkpoint adds real creation, assignment and exclusive self-claim commands through
fresh human proof, current transaction-time authority and AtomicCommands. Real-file tests cover
initial-default/definition/occurrence rollback, current override authority, restart, bounded active
assignees, concurrent claims and immutable receipt replay after another person has since claimed work.
Actual offline activation also proves that production commands return historical receipts without
reapplying restored-away creation or claim.

The complete backend passes 1,957 tests, with all 5,508 statements and 1,570 branches covered across
78 authored files. The new command module has 109 statements and 24 branches, all covered; ten task
modules together have 790 statements and 260 branches. The command suite has 45 tests; with the three
restoration tests the focused run has 48. Existing 113 tooling/architecture fixtures, strict types,
formatting, the complete inward graph and local links pass. Pinned original SDD/catalog validation
retains the fourteen/109/485 planned inventory and every original task/identity/companion case row.
Execution/approval/reopening, remaining task editors, HTTP and real consumer/target acceptance are
still incomplete. Hosted current-head CI and complete Bugbot remain independent merge gates.
