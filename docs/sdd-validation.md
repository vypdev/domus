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


## Task execution and cycle command checkpoint — 2026-11-01

Progress, completion, verification and reopening now use the shared durable boundary. Current
attribution grants precede receipt lookup, while new-performance participant/dependency checks and
cycle preconditions follow it. Real SQLite tests retain pending/rejected/approved facts, configured
prerequisite gating, source causes and immutable original receipts. Fault injection rolls back both
cycle and occurrence; completion and approval/reopen races have one winner. Actual offline activation
also proves historical replay of all three cycle actions without reapplying effects.

The complete backend passes 2,003 tests with all 5,623 statements and 1,598 branches covered across
78 authored files. Ten task modules contribute 905 statements and 288 branches, all covered. The 46
new execution cases combine with creation/current-authority tests in a 114-test focused run. All 113
tooling/architecture fixtures, strict types, formatting, the complete graph and local links pass.
Pinned original SDD/catalog checks preserve the same fourteen/109/485 planned inventory and all
original case rows. Source events explicitly leave consumer delivery unconfirmed; material settlement,
review/ledger/recurrence projections, public task queries/editors/API and deployment acceptance remain
separate required work. No partial feature merge or neutral draft review is counted as acceptance.


## Task editors and owner-confirmed remainder rotation — 2026-11-01

Policy, definition, occurrence and dependency editors now share current command authorization and
bounded typed requests. Definition edits retain prior snapshots; explicit override replacement/reset
requires current configuration authority. Every graph page is validated in the writer transaction:
late-page cycles and competing opposite edges cannot commit. Real-file fault injection and actual
offline activation prove atomic rollback and historical replay of all four editors.

The complete backend passes 2,044 tests, with all 5,741 statements and 1,624 branches covered across
79 authored files. Eleven task modules account for 1,023 statements and 314 branches. The 41 editor
cases join lifecycle, authority and Domain assertions in a 223-test focused run. Strict types,
formatting, all 113 tooling/architecture fixtures, the complete graph and local links pass.
Original pinned validation preserves task/identity/Points/companion case rows and the fourteen/109/485
planned inventory. Redundant checkpoint prose was shortened to retain the unchanged SDK document
length limit; requirements and case rows were not dropped.

A35 records the owner's same-task conserved-remainder rotation default. Points tie-breaks, participant
changes and ledger/reversal/replay remain engineering gates; this is a contract decision without
Points runtime evidence. Public task queries/history/API, actual material/consumer/review projections,
UI, both deployment targets and isolated channels still need implementation/acceptance. Current-head
hosted CI and complete full-context Bugbot remain independent merge gates.

## Task queries, signed pagination and history — 2026-11-01

Application reads now expose bounded definition/occurrence summaries, current detail and action hints,
policy defaults without initialization, safe shared history and authorized own-operation lookup.
Every transaction rechecks membership/read authority. Signed cursors bind the full query context and
expire after five minutes by default; neither possession nor an action hint grants a later write.
Current and retained facts merge by durable position without duplicating current projections.
History omits raw HA identities/canonical requests, marks absent restored effects and distinguishes
generic outbox acknowledgement from actual consumer acceptance.

The final full backend run passes 2,170 tests: all 6,071 statements and 1,722 branches covered across
all 83 authored files, with exact coverage/source inventory equality. Fifteen task modules contribute
1,353 statements and 412 branches, all covered. The 126 new cases include cross-context/expired/tampered
cursors, current revocation, bounded multi-page SQL history, corrupt evidence, original configuration
and on-behalf authority, side-effect-free planning, and actual offline checkpoint activation followed
by historical lookup and deliberate fresh work. Existing coverage configuration remains unchanged.

All 113 tooling/architecture fixtures, strict types, formatting, local links and the full dependency
graph pass. The unchanged original pinned SDK validates the SDD/catalog, declared leaves and retained
case rows. Fourteen Draft SDDs/109 requirements/485 planned cases still do not count as executed product
journeys. Original source-identified measurements and historical scopes remain in the
[task evidence](evidence/task-execution-foundation.json).

This is application/SQLite evidence with explicit provider fixtures. Both task HTTP compositions,
materials/settlement, real consumers, dependency-review projection, UI/package/live HA acceptance and
isolated Stable/Edge delivery remain required. The prior editor head has fully green project CI; its
separate Copilot assessment failure is reported upstream. Current-head CI and complete full-context
Bugbot remain required before merging the finished feature. Copilot and the gateway are unchanged.

## Task HTTP in both business compositions — 2026-11-01

The shared task router now exposes 18 operations across 15 paths in native and standalone business
compositions. Strict bounded input DTOs map to the same commands/queries; response serialization and
actual composed OpenAPI remain at the outer boundary. Existing proof/session, Origin, CSRF, JSON
duplicate-key/body bounds and current authority apply. Native task GET parameters are bounded and
nonduplicate while preserving the original peer/header policy. Authentication-only preview remains
without task capability. Unsupported materials are rejected before writes.

The final full backend campaign passes 2,256 tests, covering all 6,277 statements and 1,736 branches
across every one of the 86 authored files. Source and coverage inventories match exactly. Eighteen
task modules contribute 1,529 statements and 416 branches, all covered. The 86 new HTTP/runtime cases
include both actual ASGI compositions, restricted claim/verification, editor/dependency cycles,
current revocation, outage expiry, bounded/forged input and committed-response uncertainty. Actual
offline activation followed by owned-runtime recomposition exposes historical receipts and suppresses
their absent effects even when their old outbox event was acknowledged. Explicit fake HA transports
are not owner HA adoption.

The first campaign used a task-owned directory under `/private/tmp`, whose inherited group differed
from the process group on this host. Three unchanged launcher ownership tests failed; 2,249 passed
and all runtime coverage metrics were complete. The final campaign used an isolated directory under
the user's private temporary root with the verified process group. All original ownership checks
remain unchanged and pass; no tests or runtime scope were excluded. The original failure log and
final source-identified measurements remain in the [task evidence](evidence/task-execution-foundation.json).

Strict types, formatting, local links, all 113 tooling/architecture fixtures, the full import graph
and unchanged pinned SDD/catalog checks pass. The original case rows and fourteen/109/485 planned
inventory remain intact. Materials/settlement, review projection and real consumers, UI/packages/live
HA and full first-release acceptance remain incomplete. Prior query-head CI is fully green; its
separate assessment failure is reported in Copilot #829. Finished-feature current-head CI and complete
full-context Bugbot without unresolved findings remain mandatory before merge.


## Material model and transaction-local semantic ports — 2026-11-01

Five new runtime leaves define canonical amounts, bounded Inventory-owned bindings, intent/effect
revisions, immutable submission facts, pending outcomes, scoped confirmations and explicit
correction/dismissal. The application processor uses current-authority and Inventory ports, never
stock arithmetic or a synthetic ledger. Missing actual quantity differs from explicit zero; separate
recording requires an explicit later action. Corrected totals need actual matching confirmation,
and cannot reuse an immutable prior movement/operation identity.

All 144 new pure/port cases pass with all 346 statements and 134 branches covered across the five
material modules. The final complete backend passes 2,400 tests, with all 6,624 statements and 1,870
branches covered across all 91 authored files; coverage/source inventories match exactly. Twenty-three
task modules contribute 1,875 statements and 550 branches, all covered. The 127-file/729-dependency
inward/acyclic graph, strict types/formatting, links, all 113 tooling/architecture fixtures and original
pinned SDD/catalog checks pass. Original case rows and fourteen/109/485 planned inventory remain.

The inner model/processor and explicit absence adapter are tested with labeled semantic port fakes.
No material persistence, HTTP support, stock ledger or real-consumer delivery is implied. Those are
required next integrations. An independent schema-5 SQL input was prepared from immutable 17ea907
and checked by that same runtime after real checkpoint/activation: one closed cycle remains, with a
later completion retained as historical and absent from current state. It is preserved for the next
migration, not generated from a later schema or counted as a new migration passing.

The previous HTTP head has complete project CI; its separate Copilot assessment rejection is
reported upstream without modifying Copilot or weakening acceptance. Finished-feature current-head
CI and complete full-context Bugbot with no unresolved findings remain mandatory before merge.


## Material SQLite and canonical read checkpoint

Schema 6 now persists cycle/line-unique material intents with scoped foreign keys, immutable source
and effect guards, exact CAS and strict codecs. Definition/occurrence documents explicitly migrate
from version 1 to version 2; normal current reads never guess omitted materials. Checkpoint inspection
rejects intents detached from their original cycle/line/recorder/time/mode; reopening retains them.
The original frozen schema-5 SQL is 41,026 bytes with SHA256
`d93e1cbfb0547b53308ee6ac485ca895c0269dd286c29656618da60d5c20de50`, generated and
reopened using immutable 17ea907. Real migration preserves receipts/audit/events/cycles/retained
facts byte-for-byte, including the historical completion; actual original-key TaskCommands replay
returns its original absent effect. Failed DDL/document translation rolls back the old database.
Actual old checkpoint inspection/offline activation upgrades only its prepared target and retains
source/checkpoint bytes and the schema-5 rollback checkpoint.

Outer read DTOs and compact definition-edit evidence emit canonical decimal strings in both actual
ASGI compositions. Existing OpenAPI paths/security/schema values remain, with additive material
response facts. A 32-line maximum-size snapshot and compact audit/event budget are exercised.
The first full interim campaign found two original contract snapshot failures (2,454 passed);
canonical quantity tests then reproduced nested value objects in reads and edit receipts. The DTO
and compact-output fixes retain the original equality assertions. The original failure report is
separate from the final passing source measurements.

The final complete backend passes 2,459 tests and covers all 6,774 statements/1,898 branches across
all 95 authored files. All source files appear in the produced coverage inventory. Fifty-nine new
executions cover storage, migration, rollback, corruption, original retry, bounds and both read/edit
compositions. The 27 task modules cover 2,018 statements/578 branches. Strict types/formatting,
113 tooling/architecture fixtures, the 131-file/763-dependency inward/acyclic graph, local links and
original pinned SDD/catalog validation pass; all original case rows remain unchanged.

This checkpoint does not provide material selection/completion/settlement commands, material write
DTOs, actual Inventory movements, owner HA/UI/package adoption or complete product acceptance.
Current material-task authority binding, original-request compatibility under the later new fields,
compound CAS transitions and consumer/review projections remain required next work. The previous
material-core head has fully green project CI; its recurring Copilot assessment rejection is reported
upstream unchanged. Finished-feature current-head CI and complete Bugbot without unresolved findings
remain mandatory before merge.

## Material request and initial completion checkpoint

Typed application requests now select Inventory references/quantities and report actual usages of
frozen lines. Omitted/null new fields stay absent from canonical documents; explicit empty arrays
remain distinct. Original schema-5 completion replay still passes. Strict immutable-evidence decoding
accepts the exact known old/new shapes and rejects malformed, duplicate or noncanonical material data.
Current Inventory authority is required again for linking and original receipt disclosure.

Initial completion validates all usage identities/precision, retains one intent per frozen line,
checks current scoped/general authority and saves cycle/work/intent/CAS/receipt/audit/outbox under one
writer. Missing actual, explicit zero, separate recording, denied, shortage, changed binding and
unavailable outcomes remain distinct. Approval/reopen/retry never consumes again. The semantic
absence default has one pure implementation with a compatibility outer alias; no stock calculations
or provider I/O enter inner layers.

All 77 new cases pass, including attached fictional SQL effect/task rollback, contention, actual
commit/lost return, mixed lines, current grants, strict new audit fields, bounded maximum outcomes
and actual main-database offline activation with historical material completion replay. Confirmations
are explicit semantic fakes; the attached SQL fixture is not real Inventory or coupled ledger restore.
A binding-unavailability regression initially failed instead of saving valid work; the known absence
now becomes pending processing while unexpected failures still roll back. HTTP material write/settlement
and current/historical query integration, confirmed-correction policy review, actual consumers and
all UI/deployment acceptance remain incomplete.

The final full backend passes 2,536 tests with all 6,896 statements/1,934 branches covered across
all 96 authored files. The 28 task modules cover 2,140 statements/614 branches. Strict types/formatting,
113 tooling/architecture fixtures, the 132-file/781-dependency inward/acyclic graph, links and original
pinned SDD/catalog checks pass. All case rows and fourteen/109/485 planned inventory remain intact.
The previous persistence head has complete project CI; original upstream Copilot failures remain
separate and unchanged. Current-head project CI and complete Bugbot without unresolved findings
remain mandatory before merge.

## Material HTTP and original-cycle query checkpoint

The next increment over ae665a7 maps strict selections/usages through both actual business HTTP
compositions. Unknown fields, numeric/aliased quantities, duplicate/foreign lines, overlong lists
and unit-precision violations fail before work effects. Linking, original-key replay and clearing
recheck current Inventory authority. Provider absence fails nonempty linking atomically with 503;
valid performed work retains pending usage. Malformed confirmations roll back even attached child
SQL effects and return a safe 500 without provider details.

Current detail and the explicit original-cycle material GET share one pure source-integrity rule
with checkpoint inspection. Reads validate the full bounded frozen line set and its original
scope/recorder/time/mode, return frozen line order, recheck task-read grants and never call Inventory.
Closed-cycle outcomes stay inspectable after reopen. Pending corrections distinguish the desired
quantity from the last confirmed quantity/effect/time. Original compact receipt results remain
unchanged. Actual ASGI OpenAPI was regenerated deterministically; all original paths/security/schema
values remain, with three optional input fields, TaskDetail.materials, one GET path and six schemas
added. A36 now permits confirmed-consumption correction by any currently authorized material
participant; explicit settlement commands remain the next required implementation.

All 105 new cases and the complete backend pass: 2,641 tests, all 6,965 statements/1,942 branches
across all 98 authored files; exact source/coverage inventories match. Thirty task modules cover all
2,209 statements/622 branches. Strict typing, formatting, the 134-file/795-dependency inward/acyclic
graph and 113 tooling/architecture fixtures pass. Original pinned SDD/catalog checks retain all
planned case rows. An earlier run had three launcher ownership failures because /private/tmp
inherited GID 0 while the process used GID 20; no test or ownership guard changed. The final complete
run uses a verified private temporary parent with the process's actual group. Original interim and
final measurements are retained separately in the source-identified evidence archive.

No real Inventory ledger, product UI/package/owner HA acceptance or completed first release is
implied. Explicit post/correct/dismiss, dependency review and real consumers remain required.
Current-head hosted CI and complete full-context Bugbot without unresolved findings still gate merge.
