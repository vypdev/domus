# Decisions and readiness

Confirmed owner requirements are recorded in [product vision](product-vision.md). They are not open questions.

| ID | Proposed decision | Reason / evaluated alternative | Readiness gate |
|---|---|---|---|
| A1 | Modular backend App/Container plus thin HA companion integration | Full UI and durable domain model; pure custom integration has a larger Core lifecycle burden | Architecture review |
| A2 | Python/FastAPI, SQLite, Lit/TypeScript/Vite | Observed gateway affinity; React remains possible if calendar/mobile evidence supports it | Stack review |
| A3 | One household and one DB writer per installation | Avoid distributed consistency and preserve a migration seam | Data review |
| A4 | Verify individual HA user identity in both deployment targets; no local passwords/PINs | Meets confirmed own-account requirement; Ingress headers alone require a proven trusted boundary | Authentication spike and security review |
| A5 | Fixed schedules preserve anchors; relative schedules use accepted completion | Prevent accidental recurrence drift | Product review |
| A6 | DST gaps skip, folds choose first instant by default | Explicit deterministic proposal compatible with a bounded calendar rule model | Product review with DST preview |
| A7 | Fixed-total equal collaborative points with deterministic integer remainder | Avoid multiplying the award by participant count | Participation review |
| A8 | Manual shopping demand additional by default; reservation already included in availability | Avoid silent loss of user intent and double-counted materials | Stock/shopping review |
| A9 | Human HA context mapped to roles; automation uses narrow technical grants | Context does not establish per-MCP-client identity automatically | Service authorization review |
| A10 | HA automations orchestrate initial conditions; Domus owns deterministic commands | Avoid two competing automation engines and loops | Automation review |
| A11 | Isolated domus/domus_edge namespaces and credentials in both targets | Stable and Edge can coexist safely | Packaging and HA registry review |
| A12 | 100% supported first-party coverage metrics, with behavior-driven cases | Owner requires maximum coverage from the first code; no blanket exclusions | Quality toolchain review |
| A13 | Draft catalog retains empty implementation evidence until it exists | Audited SDK validator rejects empty code/entrypoints/tests even for proposed capabilities | Gate readiness blocked; do not change Copilot |
| A14 | Barcode scope remains provisional beyond the supplied brief | Source attachment ends at 10.2 | Obtain missing requirements before inventory readiness |

All ten SDDs remain Draft. Review resolves choices; it does not claim implementation or live acceptance.
The Copilot limitation is an observed constraint, not permission to change its implementation,
installed files, statuses, or checks. Documentation can be reviewed through its existing documentation workflow.
