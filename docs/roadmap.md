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
Test, user documentation and failure recovery travel with each change.
PR #3 merged the documentation foundation into develop. Issue #4 begins M1 with locked development
toolchains, tested quality policies and the project CI Check workflow. This is partial M1 evidence;
the complete identity/persistence journeys, real HA coverage and channel acceptance remain pending.
No implementation begins on an invented branch: maintainers and the Action retain their installed lifecycle.
Issue #6 now has its Action-published companion and verified branch. Its first source checkpoint adds
the tested SQLite transaction kernel, semantic ports, separate backend coverage and actual import graph.
The next checkpoint adds pure identity/permission rules, current local authorization, uniquely linked
member/policy storage, schema 2 migration and bounded session leases. HA protocol adapters now have
provider/loopback evidence. Standalone browser/session authentication and its HTTP/CLI entrypoints
now have executable offline coverage. Membership use cases, recovery, snapshots,
business HTTP/console entrypoints and deployment acceptance remain
incomplete M1 work; the source checkpoint does not complete M1 or change first-release scope.
Release, merge and deployment require the existing maintainer flow and explicit authorization.
Future optional depth includes predictive consumption, workload recommendations, rich rewards and external calendars.
