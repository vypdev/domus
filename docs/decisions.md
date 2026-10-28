# Decisions and readiness

Confirmed owner requirements are recorded in [product vision](product-vision.md). They are not open questions.

| ID | Decision / status | Reason / evaluated alternative | Readiness gate |
|---|---|---|---|
| A1 | Accepted: modular backend App/Container plus thin HA companion integration | Full UI and durable domain model; pure custom integration has a larger Core lifecycle burden | Owner confirmed 2026-10-29; implementation boundary checks remain required |
| A2 | Accepted: Python/FastAPI, SQLite and Lit/TypeScript/Vite; HA-coherent owned components, Storybook and Playwright | Converges with Gateway's implementation and Symphonia's accepted presentation contracts | Owner confirmed 2026-10-29; exact versions and supported-browser evidence remain required |
| A3 | Accepted: one household per installation; one DB writer proposed | Avoid distributed consistency and preserve a migration seam | Household scope confirmed 2026-10-29; storage concurrency verification remains required |
| A4 | Verify individual HA user identity in both deployment targets; no local passwords/PINs | Meets confirmed own-account requirement; Ingress headers alone require a proven trusted boundary | Authentication spike and security review |
| A5 | Accepted: relative intervals use actual completed_at; per-task successor timing defaults to at_completion with at_verification available; fixed schedules preserve calendar anchors | Approval controls points and the optional release gate, never silently shifts the recurrence anchor | Owner confirmed anchor and configurable timing 2026-10-29; state/reopening fixtures remain required |
| A6 | Owner-confirmed gap policy: advance to the first valid local instant at or after the intended time; first-instant fold policy remains proposed | Do not lose work in a daylight-saving gap; preserve the nominal occurrence identity and disclose the adjusted execution time | Gap policy confirmed 2026-10-29; fold and RRULE interoperability review remain open |
| A7 | Accepted: allocation is configurable in the application; conserve_total is the initial default, with rounded equal shares, decimal shares, full_per_participant and authorized manual allocation | The owner's later clarification permits totals below, equal to or above the base task value; policy/version and actual shares are immutable award evidence | Expanded owner decision confirmed 2026-10-29; exact remainder fairness and reward review remain open |
| A8 | Accepted default: manual shopping demands are extras; automatic inventory/material needs consolidate without counting the same need twice | Keep user intent while retaining automatic-source identities and already-reserved quantities | Owner confirmed 2026-10-29; unit conversion and detailed overlap fixtures remain engineering review |
| A9 | Human HA context mapped to roles; automation uses narrow technical grants | Context does not establish per-MCP-client identity automatically | Service authorization review |
| A10 | Accepted: one Domus declarative motor with simple/default and optional advanced editors, both at first release; HA can also call public Domus actions | One versioned model preserves behavior between editors; engine policy stays separate from native HA transport | Owner confirmed 2026-10-29; DSL bounds, recovery and loop/permission evidence remain required |
| A11 | Isolated domus/domus_edge namespaces and credentials in both targets | Stable and Edge can coexist safely | Packaging and HA registry review |
| A12 | 100% supported first-party coverage metrics, with behavior-driven cases | Owner requires maximum coverage from the first code; no blanket exclusions | Quality toolchain review |
| A13 | Draft catalog retains empty implementation evidence until it exists | Audited SDK validator rejects empty code/entrypoints/tests even for proposed capabilities | Gate readiness blocked; do not change Copilot |
| A14 | Accepted: camera scan, manual entry, local catalog and optional Internet product lookup | Local operation remains useful without an external provider; candidates retain provenance and require schema validation | Owner completed barcode scope 2026-10-29; provider feasibility/terms, library and device evidence remain required |
| A15 | Accepted defaults: adults complete without verification; restricted performers need adult approval | Resolve effective verification from the actual performers and authorized policy, not just the submitter's role | Owner confirmed 2026-10-29; explicit task overrides and permission contracts require tests |

All eleven SDDs remain Draft. Review resolves choices; it does not claim implementation or live acceptance.
The Copilot limitation is an observed constraint, not permission to change its implementation,
installed files, statuses, or checks. Documentation can be reviewed through its existing documentation workflow.

## Owner decisions recorded on 2026-10-29

- Nonexistent local task times advance to the first valid instant at or after the intended wall time on that date. For example, a 02:30 task in a 02:00–03:00 clock gap runs at 03:00, not at midnight and not twice. The adjustment is visible and retains the nominal occurrence key.
- Collaborative points are configurable in the application. The initial default shares one conserved total, but households may select equal shares rounded down/up, decimal shares, full task points per participant or authorized manual amounts. For a base of ten and three performers, supported examples include 3/3/4, 3/3/3, 4/4/4, 3.33/3.33/3.33 and 10/10/10. This later clarification supersedes conservation as a universal invariant. Award history retains base value, policy/version, precision, shares and actual total.
- The owner confirmed Lit/TypeScript/Vite, a Home Assistant-coherent visual direction with Domus-owned presentation components, Storybook and Playwright after reviewing Symphonia and Gateway. Their examples are evidence, not a private HA component dependency or an inherited version/support promise.
- The owner confirmed Python/FastAPI, SQLite, a thin HA integration and one household per installation. Exact toolchain versions, migrations, authentication proof and writer concurrency remain engineering verification gates.
- Adults need no task-completion verification by default; restricted performers need approval by an authorized adult. Points wait for that required approval. Explicit administrator-controlled overrides remain a documented configuration concern.
- Barcode entry includes camera scan and manual input, local matching and optional Internet lookup. The provider itself remains unselected pending feasibility, terms and security review.
- Completion-relative schedules anchor to actual completed_at; a delayed approval never shifts the next scheduled date.
- Manual shopping requests are additional by default. Automatic stock/material requirements consolidate against their source/coverage identity without counting the same need twice.
- Both automation editors are first-release features: simple is the default and advanced is optional. They share one declarative engine; switching editor cannot discard advanced rule fields.
- Successor timing is configurable per task: show it when completion is recorded by default, or wait for approval. Both choices calculate its date from actual work completion; waiting for approval does not move that date.
