# Domus — Your home. In harmony.

Domus is a local household management application for Home Assistant. It unifies tasks,
calendar planning, shopping, inventory, family participation and automation through its own UI.
Ordinary workflows work without AI, external calendars or Internet services.

## Confirmed owner decisions

- The first usable release covers all six functional domains.
- Both Supervisor-managed App/Ingress and standalone Container are first-release targets.
- Every participating member has their own Home Assistant account.
- The existing gateway is already integrated in HA. Domus defines entities and services for it to consume.
- All issues, documentation, code, identifiers and comments are English; conversation with the owner is Spanish.
- Clean Architecture is mandatory. Every implementation starts with tests and maximum coverage.
- Stable production and experimental development channels are required, as in the gateway.
- A project workflow named CI Check runs all tests on each PR update.
- Google Chrome dogfooding is authorized at http://homeassistant.local:8123/.
- Copilot is immutable, except a narrowly reviewed project dependency-preparation setup file if needed.
- Nonexistent local task times advance to the first valid instant at or after their intended wall time; the task is not silently dropped (confirmed 2026-10-29).
- Collaborative allocation is configurable in the application: conserve one task total by default, or choose rounded/decimal equal shares, full points per participant or authorized manual shares. Show the actual total and preserve the chosen policy with each award (expanded owner decision 2026-10-29).
- The selected architecture is Python/FastAPI with SQLite, a thin HA companion integration and one household per installation (confirmed 2026-10-29).
- The UI uses Lit/TypeScript/Vite, Domus-owned HA-coherent components, a Storybook catalog and Playwright browser tests (confirmed 2026-10-29).
- Adults complete tasks without verification by default; restricted performers need adult approval before points are awarded (confirmed 2026-10-29).
- Barcode workflows include camera scan, manual entry, local catalog search and optional Internet product lookup; no external provider is mandatory (confirmed 2026-10-29).
- Completion-relative schedules count from actual work completion rather than its later approval (confirmed 2026-10-29).
- Manual shopping requests are extras by default; automatic inventory/material needs consolidate without double-counting a source requirement (confirmed 2026-10-29).
- Simple/default and optional advanced automation editors are both included in the first release over one shared declarative engine (confirmed 2026-10-29).
- Relative tasks show their next occurrence when work is recorded by default; each task may instead wait for approval without changing the actual-completion date anchor (confirmed 2026-10-29).
- Material quantities are reviewed and adjustable when completing a task, with both recorded in the same submission; the task configuration can use separate recording instead (confirmed 2026-10-29).
- Material stock shortfalls do not block recording performed work: save consumption pending regularization without inventing negative stock (confirmed 2026-10-29).
- Reopening reverses the actual point award even if spent; a factual negative balance blocks new redemptions until recovered while delivered rewards remain delivered (confirmed 2026-10-29).
- Missed fixed-schedule occurrences are configurable per task; the default keeps all visible with explicit skip available, retaining history without completion points (confirmed 2026-10-29).
- Recurrence changes show a preview and update only future executions that have not started, preserving started work and history (confirmed 2026-10-29).
- Participation and earned points belong to the actual-work period; required approval controls when points become spendable without moving them to the approval week (confirmed 2026-10-29).

## Source boundary

The attachment contains sections 1–10.1 and the beginning of 10.2. It ends after
“Support common product identifiers such”. Missing text is not treated as an instruction.
The owner completed the barcode scope on 2026-10-29 as recorded above; provider/library selection,
lot allocation and several limits still require explicit engineering proposals and review.

## Connected domains

| Domain | Authoritative facts | Cross-domain link |
|---|---|---|
| Household tasks | Definitions, occurrences, assignments and actual completion | Calendar, materials and point awards |
| Family calendar | Schedules, exceptions and date/time projections | Task occurrences and completion history |
| Shopping | Demands, planning, purchases and physical receipt | Materials and replenishment |
| Inventory | Product identity, presentations, locations and stock ledger | Receipt, consumption and demand |
| Family and participation | Verified HA identity mapping, permissions and points ledger | Authorship, effort and optional rewards |
| Automation and intelligence | Deterministic HA-facing triggers, actions and audit | All domain commands, without a second MCP |

Maintenance is represented through tasks, linked equipment/entities and material requirements.
Initial inventory prioritizes durable products while optional lots allow later perishable tracking.
Rewards, predictions and external calendar sync remain optional advanced extensions as described in the brief;
all domains themselves are included at launch.

## Product boundaries

Local-first means a local authoritative server and owned data, not an unreviewed offline-write sync protocol.
One household per installation is confirmed. Child/restricted members still use their own HA accounts.
A person entity is optional profile/presence metadata and never a login.
Points help explain participation; task counts, estimated effort and workload remain visible.

## First integrated release acceptance

A member creates a scheduled maintenance task requiring a stock item, claims/completes the occurrence,
records material consumption, earns verified ledger points, sees the calendar/history, receives a low-stock
shopping requirement, purchases and receives the replacement, and verifies HA entities/services.
The same business fixtures pass on both deployment targets and channels. Internal milestones are not separate
partial product releases. See [roadmap](roadmap.md) and [architecture](architecture.md).
