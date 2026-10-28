# Domus — Intelligent Household Management

**Your home. In harmony.**

Domus is a local-first household application for Home Assistant, bringing tasks,
calendar planning, shopping, pantry inventory, family participation and automation
into one responsive interface. Normal operation does not require AI or cloud services.

## Project status

Domus is in the specification phase. No application is implemented or published yet.
The [documentation foundation issue](https://github.com/vypdev/domus/issues/2)
tracks ten Draft SDDs, 71 normative requirements and 213 planned acceptance cases.
These cases are verification plans, not executed application tests.

The first usable release covers all six domains, Supervisor App/Ingress and
standalone Container, and isolated Stable and experimental Edge channels.
Every participant uses their own Home Assistant account. The existing HA gateway
is already integrated; Domus supplies native entities and services and does not
implement another MCP server.

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

## Quality and contribution

Clean Architecture is mandatory. Meaningful tests accompany every implementation
from its first change, with 100% supported first-party coverage metrics as the
proposed enforced gate. A future project-owned workflow named **CI Check** runs
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
format and consistency checks pass. The proposed SDK catalog still fails the unchanged
upstream evidence validator because application entrypoints, source and tests do not
exist yet; no fake paths or gate-readiness claims are used. See the
[adoption note](docs/copilot-adoption.md).

The supplied brief ends at the beginning of section 10.2; inventory readiness requires
reviewing the missing barcode requirements. No application build/test commands or CI
workflow are installed by this documentation-only change.
