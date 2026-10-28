# Validation evidence

Audited 2026-10-28. This is documentation validation, not application acceptance.

| Check | Result | Meaning |
|---|---|---|
| Original twenty-section headings | PASS — 10/10 | Exact comparison with the unmodified upstream template |
| Original draft format validator | PASS — 10/10 | Required headings, supported length and numeric budget |
| Original consistency validator | PASS — 10/10 | Case IDs, per-area budgets, reciprocal requirement links and declared paths |
| Original prerequisite structure policy | PASS | The unchanged reference standard/template meet the required structure |
| Local document links | PASS | All local Markdown file links resolve; original template placeholders are excluded |
| Original SDK catalog validator | BLOCKED — 30 errors | No implemented entrypoints, source or tests exist for the proposed capabilities |
| Upstream policy provenance | PASS — 7/7 | Source copy Git blob IDs match fetched upstream files |
| Copilot installation | Unchanged | No installed Copilot resources or implementation were edited |
| Application tests / coverage | Not implemented | Planned cases are not executed tests |
| Real Chrome dogfooding | Not run | Requires an implemented identifiable artifact |
| Product readiness | Draft | Review decisions and catalog evidence prerequisites remain open |

## Per-SDD results

| Capability | Requirements | Planned cases | Original format/consistency |
|---|---:|---:|---|
| platform-foundation | 6 | 18 | PASS |
| household-identity | 6 | 18 | PASS |
| household-tasks | 8 | 24 | PASS |
| recurrence-calendar | 8 | 24 | PASS |
| points-rewards | 6 | 18 | PASS |
| shopping-management | 7 | 21 | PASS |
| household-inventory | 8 | 24 | PASS |
| home-assistant-surface | 8 | 24 | PASS |
| application-experience | 6 | 18 | PASS |
| delivery-quality | 8 | 24 | PASS |

Totals: 71 normative requirements and 213 planned distinct cases.

## Catalog limitation

The unchanged SDK validator requires nonempty entrypoints, code and tests arrays even when status is proposed.
Ten proposed capabilities therefore produce thirty missing-evidence errors; no other catalog errors were returned.
The original renderer generated CATALOG.md as an ownership view, which does not override validation.
No fake paths, status changes, schema substitution, weakened checks or Copilot edits were used.
The initial package can be reviewed through the existing documentation workflow; no automatic feature gate readiness is claimed.

## Reproduction and provenance

Copilot revision: f5e5a4cf9a80248994469cd88ad55eecab5b95ca.
The original validateSddMarkdown, validateSddDraftConsistency, validateSddPrerequisiteDocuments and validateCatalog
functions were executed from byte-verified copies. TypeScript was transpiled in memory to CommonJS;
no policy source was edited. Original case consistency also checked the new documentation paths against
the actual tracked repository baseline. All twenty headings were independently compared to the unchanged template.

To reproduce independently, fetch the seven exact upstream files listed in the evidence JSON, verify their Git blob hashes, transpile TypeScript without editing policy source, and invoke the original format, consistency and catalog functions against the proposed documents and the tracked base-tree inventory. The standard and template are also unchanged upstream copies. The format/consistency functions are named above; repository layout and case tables are fully declared in each SDD. No custom validator can replace the Action's bundled authority.

[Raw results and source provenance](evidence/sdd-validation.json) include upstream Git blob and local SHA-256 hashes. No release, deployment or live compatibility acceptance follows from these checks.
