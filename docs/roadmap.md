# Development sequence and first-release gate

The first usable release includes every functional domain, both deployment targets and both channels.
The following milestones are internal integration steps, not proposals to drop launch scope.

| Milestone | Contract and implementation | Exit evidence |
|---|---|---|
| M0 — Specification foundation | Research, vision, eleven Draft SDDs, decisions and review | Format/traceability checks; explicit unresolved items |
| M1 — Tested platform | Identity, persistence, architecture rules, CI Check and channel isolation | 100% supported coverage; restart, migration and deployment fixtures |
| M2 — Household work | Members, tasks, recurrence, calendar, points | Complete/reopen/verify/replay races and localized UI |
| M3 — Household supplies | Products, stock ledger, demand, purchase and receipt | End-to-end material and replenishment consistency |
| M4 — Automation and HA surface | One durable engine, simple/default and optional advanced editors, entities and response services across domains | Replay/restart/loop/partial-run cases plus disposable-HA contracts in both deployment targets |
| M5 — Integrated acceptance | Dashboard, responsive UX, access control, Stable/Edge packaging | Full CI Check; local Google Chrome dogfooding and recorded cleanup |

The product is not considered first-release complete at M2 or M3.
Tests, user documentation and recovery accompany each usable workflow.

Current state after PR #28:

- M0: the specification foundation and decisions are recorded. Contracts continue to evolve with implementation evidence.
- M1: HA identity/session, SQLite, recovery foundations, architecture checks and CI are implemented. The full standalone/Ingress, upgrade/restore and Stable production acceptance remains open.
- M2: household administration is usable in Edge.7. Task creation, assignment, claiming, completion, verification, reopening, dependencies and material recording exist in the backend. Fixed recurrence execution and relative-rule storage exist. Task and calendar screens, the relative lifecycle consumer, configurable point distribution and complete participation/reward flows remain open.
- M3: task-material foundations exist. Integrated product, stock, shopping, receipt, barcode and optional online lookup workflows remain open.
- M4: the shared automation engine, both editors and Domus-owned HA entities/services remain open. The existing gateway is already integrated and is outside this work.
- M5: integrated dashboard, complete responsive UX, both deployment journeys and Stable release acceptance remain open.

The next M2 sequence is a usable task workspace (create, list, inspect, complete and review), then recurrence and calendar, then points and participation. Technical records stay available in optional details. Each increment must have real UI and persistence evidence; coverage of implemented code is not a measure of whole-product completion.

PR #29 / issue #23 retains all recurrence/calendar obligations. Its initial genuine schema-9 fixture is a migration baseline, not evidence that the relative lifecycle or calendar is implemented. Household administration's remaining full acceptance inventory also remains required after its checkpoint merge.

The Action owns managed remote branches. Normal contributor commits use its admitted ref; release and deployment use the authorized maintainer flow.
Future optional depth includes predictive consumption, workload recommendations, rich rewards and external calendars.
