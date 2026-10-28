# Validation evidence

Audited 2026-10-29. This is documentation validation, not application acceptance.

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
| platform-foundation | 6 | 18 | PASS |
| household-identity | 6 | 18 | PASS |
| household-tasks | 8 | 27 | PASS |
| recurrence-calendar | 8 | 28 | PASS |
| points-rewards | 6 | 27 | PASS |
| shopping-management | 7 | 21 | PASS |
| household-inventory | 8 | 28 | PASS |
| home-assistant-surface | 8 | 24 | PASS |
| application-experience | 6 | 24 | PASS |
| delivery-quality | 8 | 24 | PASS |
| household-automation | 9 | 42 | PASS |

Totals: 80 normative requirements and 281 distinct planned cases across eleven SDDs.
The owner-confirmed automation scope adds one engine capability with 42 planned cases; the HA surface remains the adapter owner.

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
