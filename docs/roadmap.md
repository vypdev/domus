# Development sequence and first-release gate

The first usable release includes every functional domain, both deployment targets and both channels.
The following milestones are internal integration steps, not proposals to drop launch scope.

| Milestone | Contract and implementation | Exit evidence |
|---|---|---|
| M0 — Specification foundation | Research, vision, SDDs, decisions and review | Native format/traceability checks; explicit unresolved items |
| M1 — Tested platform | Identity, persistence, architecture rules, CI Check and channel isolation | 100% supported coverage; restart, migration and deployment fixtures |
| M2 — Household work and shared presentation | Shared presentation package and upper tab shell first; members, tasks, recurrence, calendar and points | Common component adoption; complete/reopen/verify/replay races; localized usable journeys |
| M3 — Household supplies | Products, stock ledger, demand, purchase and receipt using the common components | End-to-end material and replenishment consistency |
| M4 — Automation and HA surface | One durable engine, simple/default and optional advanced editors, entities and response services across domains | Replay/restart/loop/partial-run cases plus disposable-HA contracts in both deployment targets |
| M5 — Integrated acceptance | Complete household overview, cross-domain UX/accessibility, access control, Stable/Edge packaging | Full CI Check; local Google Chrome dogfooding and recorded cleanup |

The product is not considered first-release complete at M2 or M3.
Tests, user documentation and recovery accompany each usable workflow.

## Current state

As of 2026-11-04, with PR #29 still under development:

- M0: the specification foundation and decisions are recorded. Contracts continue to evolve with implementation evidence.
- M1: HA identity/session, SQLite, recovery foundations, architecture checks and CI are implemented. Full standalone/Ingress, upgrade/restore and Stable production acceptance remains open.
- M2: task creation, claiming, completion, review and reopening are usable in the owner's Edge.9 through Ingress, alongside household administration. English/Spanish and task/preference persistence were exercised after reload. The backend also has dependency/material foundations, fixed recurrence execution, relative-rule creation/storage a tested pure cycle-closure policy an atomic initial relative-materialization service and closed lifecycle storage encoding. The durable relative consumer, calendar/recurrence editors, full task editors, configurable point distribution and complete participation/reward flows remain open. The pure policy and initial service are not yet wired into maintenance.
- M3: task-material foundations exist. Integrated product, stock, shopping, receipt, barcode and optional online lookup workflows remain open.
- M4: the shared automation engine, both editors and Domus-owned HA entities/services remain open. The existing gateway is already integrated; its MCP/business behavior is outside this work.
- M5: complete cross-domain overview/acceptance, both deployment journeys and Stable release acceptance remain open. Foundational UI reuse is scheduled in M2, not deferred to this final milestone.

## Shared components, Domus-owned experience

The owner's clarification on 2026-11-04 is a fixed product direction: Domus and Home Assistant
Gateway reuse one maintained presentation component package. The common navigation pattern is the
upper tab bar used by Gateway and current HA dashboards. Domus owns its section structure, page
composition, information hierarchy, wording and household workflows; it does not copy Gateway's
technical/MCP dashboard.

[ha-ui issue #7](https://github.com/vypdev/ha-ui/issues/7) owns the shared component/adapter contract.
[Domus issue #30](https://github.com/vypdev/domus/issues/30) owns consumer adoption and the Domus shell. Gateway currently has local Lit primitives/layouts under frontend/src/ui, not an
independently published dependency. Reusable styles are split between application and catalog files.
The first step is therefore a coherent extraction with one source and versioned public API, followed
by actual adoption in both apps. Copying components/CSS into Domus is not completion of reuse.

The chosen ownership/delivery direction is a dedicated vypdev/ha-ui repository, an independently
versioned @vypdev/ha-ui npm package, and its own static component Storybook on GitHub Pages. The
repository now exists, and the official web-generated Copilot installation has been reviewed and
merged into master and develop. The packages and Storybook remain unimplemented and unpublished;
publisher rights and source-to-artifact integrity must be verified before publication. The library owns its tests, API compatibility and
catalog. Both apps consume exact reviewed versions and may upgrade independently within tested
compatibility. Storybook is built from the same component implementation, with reviewable PR catalog
builds. Domus retains app-level stories for its own composed household pages.


The owner requires delivered React, Vue, Angular and Svelte adapter packages alongside direct Lit
and HTML/JavaScript consumption. Keep their public interaction contract on DOM properties,
attributes, slots, typed events and CSS theme tokens. Lit is the common implementation tool;
application-specific render callbacks and TemplateResult values do not enter the common API.
Each adapter has only its own framework dependencies and delegates visual/accessibility behavior
to the same core. Keep one repository, one component Storybook and a compatible version cohort.

Before broad extraction, prove actual packed-package consumption in compiled Lit/DOM, React, Vue,
Angular and Svelte fixtures with browser and type checks. Test events, complex property updates,
slots, lifecycle, disabled/focus behavior, themes and forms integration. Document and verify the
supported version matrix and Next.js/Nuxt/SvelteKit client/import boundaries; generic Web Component
interoperability does not establish SSR or hydration acceptance. Core and adapter implementations
start with tests and complete supported coverage. Preserve Gateway's MIT source notices and asset
provenance. Package publication and adoption in each app remain separate gates.

The shared package owns presentation tokens, type/spacing scales, tabs, buttons, fields, selects,
checkboxes, cards, rows/grids, dialogs and feedback states. Each app owns its controllers, routing,
permissions, domain models, API clients and data. Package changes must not require Gateway to run,
read parent DOM/private storage, load HA private bundles or widen authentication/API permissions.
All reviewed component code/assets are bundled for both Ingress and standalone.

| Planned Domus section | Household purpose |
|---|---|
| Overview | First destination: today's/overdue/my/unclaimed work, upcoming maintenance, shopping/stock attention and household participation, with useful next actions |
| Tasks | Create, assign, claim, perform and review work; manage recurring definitions and their per-task policies |
| Calendar | Explore actual planned/due/performed/approval facts and recurring obligations by date; link back to the owning task |
| Shopping | Consolidated requirements, manual extras, purchases and receipt |
| Inventory | Products, quantities, locations, expiry, materials and replenishment |
| Family | Participants, contribution, configurable scoring/point allocation, balances and rewards |
| Settings | Household policy, preferences and authorized administration; detailed diagnostics remain secondary |

These describe the complete product architecture, not seven already implemented screens. Recurrence
editing stays with Tasks and its temporal projection stays in Calendar. Points/rewards stay with
Family, with contextual links from completed work. This avoids duplicate rule or ledger ownership.
Tabs have localized accessible names and retain the common flat active indicator, keyboard/focus and
narrow-screen overflow behavior. Their content and grouping remain appropriate to Domus.

The Overview must use authoritative, permission-scoped projections. Unavailable or incomplete data
never becomes a zero, a success badge or a household total inferred from one paginated task page.
Domain summaries and quick actions are added with the underlying workflows; no nonfunctional
placeholder is presented as a finished feature. Existing Tasks/Household entry links, private drafts,
original requests and exact revisions must survive the shell migration.

## Immediate sequence

1. Establish the native shared-package SDD, framework-neutral API and real Lit/DOM plus React/Vue/Angular/Svelte consumer fixtures. Then extract reusable Gateway presentation styles/behavior once, with Storybook and versioned artifact acceptance. Record ownership and dependency delivery before claiming extraction.
2. Adopt that same package for the Domus shell and existing task/administration workflows. Introduce the upper tabs and an actionable Overview as real scoped summaries become available. Test light/dark, EN/ES, narrow/wide, keyboard, reduced motion, Ingress and standalone. Do this before expanding additional bespoke domain screens.
3. Complete the durable relative lifecycle, shared maintenance budgets, reviewed recurrence changes and protected calendar using the common components. Backend work may continue while the presentation package is prepared.
4. Complete points, configurable distribution, participation and rewards in the Family experience.
5. Deliver M3 supplies, then M4 automation/HA surfaces, composing their screens from the same package.
6. Complete M5 integrated overview, usability, recovery and Stable/Edge acceptance. This verifies the established foundation; it is not a late design-system rewrite.

Every implemented first-party component starts with tests and complete supported coverage. The shared
catalog covers normal/loading/disabled/error/empty/dialog states and both themes/locales. Real browser
journeys must preserve current commands, drafts and original recovery in both consumers. Package
publication, consumer adoption, compiled-image acceptance and required human UX are separate evidence.

PR #29 / issue #23 retains all recurrence/calendar obligations: all 93 counted retained cases and
18 refinements remain required. The genuine schema-9 fixture and pure closure policy do not prove
the durable consumer or calendar is implemented. Household administration's remaining acceptance
inventory also remains required after its checkpoint merge. Issue #30 does not close or replace these.

The Action owns managed remote branches and native SDD publication. Normal contributor commits use
its admitted ref; package/release/deployment work follows each owning repository's authorized flow.
Copilot remains unchanged. Future optional depth includes predictive consumption, workload
recommendations, richer rewards and external calendars.
