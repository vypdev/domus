# Product capability specification catalog

> Generated from [`catalog.json`](./catalog.json). Do not edit this table by hand.
> Run `pnpm run generate:specifications` after changing catalog metadata.

This catalog answers which product contract owns a capability and where its
implementation, verification, workflow, and user-documentation evidence lives.
An **As-built baseline** records verified current behavior; it does not hide known
debt or convert unknown historic intent into a design decision.

| Capability ID | Status | Scope | Primary SDD | Evidence |
|---|---|---|---|---|
| `platform-foundation` | Proposed | One local modular application serves the complete household product in both a Supervisor-managed App and standalone Docker from the first release. Home Assistant owns user authentication; Domus owns its business records. | [Local application platform and persistence](./platform-foundation.md) | 5 paths · 2026-10-28 |
| `household-identity` | Proposed | Each participating person uses their own Home Assistant account. Domus associates that verified user with one household member and applies explicit backend permissions independently of an optional person entity. | [Household members, Home Assistant identity and permissions](./household-identity.md) | 5 paths · 2026-10-28 |
| `household-tasks` | Proposed | Members create and perform household responsibilities with explicit assignments, actual performers and history. A recurring definition survives completion of each individual occurrence. | [Task definitions, occurrences and household execution](./household-tasks.md) | 5 paths · 2026-10-28 |
| `recurrence-calendar` | Proposed | A bounded scheduler turns task definitions into stable occurrences and a family calendar distinguishes planned start, deadline and actual completion. | [Recurrence engine and family calendar](./recurrence-calendar.md) | 5 paths · 2026-10-28 |
| `points-rewards` | Proposed | Task completion produces auditable point entries. Corrections preserve history, collaborative allocation preserves the agreed award total, and optional rewards never control basic participation. | [Auditable points, participation and optional rewards](./points-rewards.md) | 5 paths · 2026-10-28 |
| `shopping-management` | Proposed | Shopping combines manual intent, replenishment and task materials without losing provenance. Buying an item and physically receiving it are separate recorded facts. | [Shared shopping demand, purchases and receipt](./shopping-management.md) | 5 paths · 2026-10-28 |
| `household-inventory` | Proposed | The household knows what is available, where it is stored and what needs replenishment through a local product catalog and an immutable stock movement ledger. | [Product catalog, pantry stock and replenishment](./household-inventory.md) | 5 paths · 2026-10-28 |
| `home-assistant-surface` | Proposed | Domus exposes its household capabilities as native Home Assistant entities, services and events. The already integrated HA MCP consumes these surfaces; no gateway work or second MCP is included. | [Home Assistant entities, services and household automation](./home-assistant-surface.md) | 5 paths · 2026-10-28 |
| `application-experience` | Proposed | A complete household interface serves all six domains from the first release with fast daily actions, responsive navigation and clear operation results, independently of entity dashboards and AI. | [Responsive application, household dashboard and navigation](./application-experience.md) | 5 paths · 2026-10-28 |
| `delivery-quality` | Proposed | Every implemented capability starts with meaningful tests and enforced architecture boundaries. A CI Check workflow validates each PR update, and both deployment targets ship isolated experimental and production channels. | [Clean Architecture, CI Check and isolated Stable and Edge channels](./delivery-quality.md) | 5 paths · 2026-10-28 |

## Evidence map

### `platform-foundation` — Local application platform and persistence

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/platform-foundation.md`](./platform-foundation.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `household-identity` — Household members, Home Assistant identity and permissions

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/household-identity.md`](./household-identity.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `household-tasks` — Task definitions, occurrences and household execution

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/household-tasks.md`](./household-tasks.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `recurrence-calendar` — Recurrence engine and family calendar

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/recurrence-calendar.md`](./recurrence-calendar.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `points-rewards` — Auditable points, participation and optional rewards

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/points-rewards.md`](./points-rewards.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `shopping-management` — Shared shopping demand, purchases and receipt

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/shopping-management.md`](./shopping-management.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `household-inventory` — Product catalog, pantry stock and replenishment

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/household-inventory.md`](./household-inventory.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `home-assistant-surface` — Home Assistant entities, services and household automation

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/home-assistant-surface.md`](./home-assistant-surface.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `application-experience` — Responsive application, household dashboard and navigation

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/application-experience.md`](./application-experience.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

### `delivery-quality` — Clean Architecture, CI Check and isolated Stable and Edge channels

- Owner: Domus maintainers (review assignment pending)
- Last verified: 2026-10-28
- Specifications: [`specs/delivery-quality.md`](./delivery-quality.md)
- Workflows: Not applicable for this capability.
- Entrypoints: Not applicable for this capability.
- Core code: Not applicable for this capability.
- Tests: Not applicable for this capability.
- User documentation: [`docs/product-vision.md`](../docs/product-vision.md) · [`docs/architecture.md`](../docs/architecture.md) · [`docs/operations.md`](../docs/operations.md) · [`docs/user-guide.md`](../docs/user-guide.md) · [`docs/contracts/home-assistant.md`](../docs/contracts/home-assistant.md)

## Maintenance contract

1. Read the relevant SDD before changing a catalogued capability.
2. Change the SDD, catalog evidence, tests, and user documentation together when
   behavior or an architecture boundary changes.
3. Use repository-relative paths in `catalog.json`; each path is validated and every
   top-level product SDD must have exactly one capability owner.
4. Run `pnpm run validate:specifications` in local and CI validation.
