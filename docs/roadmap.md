# Development sequence and first-release gate

The first usable release includes every functional domain, both deployment targets and both channels.
The following milestones are internal integration steps, not proposals to drop launch scope.

| Milestone | Contract and implementation | Exit evidence |
|---|---|---|
| M0 — Specification foundation | Research, vision, ten Draft SDDs, decisions and review | Format/traceability checks; explicit unresolved items |
| M1 — Tested platform | Identity, persistence, architecture rules, CI Check and channel isolation | 100% supported coverage; restart, migration and deployment fixtures |
| M2 — Household work | Members, tasks, recurrence, calendar, points | Complete/reopen/verify/replay races and localized UI |
| M3 — Household supplies | Products, stock ledger, demand, purchase and receipt | End-to-end material and replenishment consistency |
| M4 — HA surface | Entities, response services and automation triggers across domains | Disposable-HA contract tests in both deployment targets |
| M5 — Integrated acceptance | Dashboard, responsive UX, access control, Stable/Edge packaging | Full CI Check; local Google Chrome dogfooding and recorded cleanup |

The product is not considered first-release complete at M2 or M3.
Test, user documentation and failure recovery travel with each change.
No implementation begins on an invented branch: maintainers and the Action retain their installed lifecycle.
Release, merge and deployment require the existing maintainer flow and explicit authorization.
Future optional depth includes predictive consumption, workload recommendations, rich rewards and external calendars.
