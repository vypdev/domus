# Domus — Intelligent Household Management

**Your home. In harmony.**

Domus is a local-first household application for Home Assistant, bringing tasks,
calendar planning, shopping, pantry inventory, family participation and automation
into one responsive interface. Normal operation does not require AI or cloud services.

## Project status

The Edge preview supports Overview, Tasks, Calendar, Inventory, Shopping, Family and Household
administration in English and Spanish. The tested workflows include recurring tasks, household
points and rewards, inventory movements and replenishment, shared shopping, and purchases and
physical receipts. Home Assistant Ingress uses the existing Home Assistant session. Both Ingress
and standalone are exercised in the application checks.

The version offered by `develop`, its immutable artifact and its installed acceptance are recorded
in the [Home Assistant installation guide](docs/installation-home-assistant.md). The
[capability catalog](specs/CATALOG.md) and [roadmap](docs/roadmap.md) track current qualification
and remaining work, including the automation engine, full integrated acceptance and Stable release.

The first usable release covers all six domains, Supervisor App/Ingress and
standalone Container, and isolated Stable and experimental Edge channels.
Every participant uses their own Home Assistant account. The existing HA gateway
is already integrated; Domus supplies native entities and services and does not
implement another MCP server.

The owner-selected stack is Python/FastAPI, SQLite and Lit/TypeScript/Vite, with
one household per installation and a thin HA integration. Domus owns HA-coherent
workspace composition, a Storybook catalog and Playwright browser contracts. The shared
Home Assistant presentation components come from `@vypdev/ha-ui`.
Simple/default and optional advanced automation editors are both launch scope,
sharing one durable declarative engine. Collaborative points allocation is configurable
in the application, with the chosen policy and actual awards preserved in the ledger.

## Read the foundation

- [Product vision and confirmed owner requirements](docs/product-vision.md)
- [Architecture, boundaries and evaluated alternatives](docs/architecture.md)
- [Capability catalog and SDD index](specs/CATALOG.md)
- [Home Assistant entities and services](docs/contracts/home-assistant.md)
- [Open architectural and product decisions](docs/decisions.md)
- [Reference investigation](docs/reference-investigation.md)
- [Development milestones](docs/roadmap.md)
- [Acceptance, coverage and CI Check plan](docs/acceptance-plan.md)
- [Specification validation evidence and limitations](docs/sdd-validation.md)
- [Development setup, tests and CI Check](docs/development.md)
- [Home Assistant app installation and development preview](docs/installation-home-assistant.md)
- [Implemented authentication journey and limits](docs/identity-household.md)
- [Authentication server configuration](docs/configuration.md)
- [Identity/storage operations and pending commands](docs/operations-identity-storage.md)

## Quality and contribution

Clean Architecture is mandatory. Meaningful tests accompany every implementation
from its first change, with 100% supported first-party coverage metrics as the
required implementation gate. The project-owned workflow named **CI Check** runs
the full applicable suite for every PR update. English is used for issues,
documentation, source identifiers and comments; the product supports English and Spanish.

Google Chrome dogfooding is authorized against the owner's local Home Assistant,
using identifiable test data and explicit cleanup. Stable and Edge data, credentials
and HA identities stay separate.

Read [the specification standard](specs/README.md) and the owning SDD before changing
a capability. Follow the existing [repository collaboration guide](.copilot/AGENT_GUIDE.md)
for Action-managed branches and linked PRs. Copilot's implementation and installed
resources remain unchanged; the owner's only narrow exception is project dependency
preparation when necessary. Merge, release and deployment remain separately authorized.

## Readiness limitations

All SDDs remain Draft while material decisions are reviewed. Their original Copilot
format and consistency checks pass. The corrected upstream catalog validator accepts truthful
proposed capabilities with empty implementation arrays. Platform, identity and delivery-quality
register only their real partial evidence; no fake paths or gate-readiness claims are used. See the
[adoption note](docs/copilot-adoption.md).

The supplied brief ends at the beginning of section 10.2. The owner completed the
barcode scope on 2026-10-29: camera/manual entry, local matching and optional Internet
product lookup. Provider feasibility and device evidence still require review.
The authentication checkpoint uses real adapters and offline provider and loopback fixtures.
Current CI and installed preview evidence are tracked for each increment in the
[acceptance plan](docs/acceptance-plan.md) and [roadmap](docs/roadmap.md).
