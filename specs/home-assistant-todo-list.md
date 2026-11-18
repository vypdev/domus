# Show open household tasks in Home Assistant

- Status: Draft
- Date: 2026-11-18
- Catalog capability ID: home-assistant-surface
- Owners: Domus maintainers
- Scope: A read-only native to-do list of currently open household task occurrences
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: none for the bounded read-only occurrence list

## 1. Executive summary

Home Assistant users can consult open Domus tasks in a native list. Each entry
identifies one occurrence and shows its title and current task state. Users manage
the work in Domus.

## 2. Problem, current behavior, and evidence

Domus has an authoritative occurrence query with an existing open-only filter.
The companion exposes calendars, deadline counts, low-stock counts and the shared
shopping list. The Home Assistant contract reserves a native task to-do projection.

## 3. Actors, surfaces, and terminology

An installation administrator can opt into a dedicated technical grant. Home
Assistant entities and dashboard users can then view the complete open household
list. A list item represents a task occurrence, including separate occurrences of
the same definition. Open follows the existing filter that excludes completed,
cancelled and skipped occurrences.

## 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
| --- | --- |
| ha-open-tasks-R01 | Read the existing open-only occurrence query from a consistent household transaction. Publish titles, current states and opaque stable occurrence identities, including beyond the first display page. |
| ha-open-tasks-R02 | Use a separate optional installation, channel and task-purpose grant. Hide member identities, task requirements, material data, completion records and ledger history. |
| ha-open-tasks-R03 | Create a stable native read-only task list per source with correct empty, unavailable and recovered states and English and Spanish display states. |
| ha-open-tasks-R04 | Verify actual Core, Ingress and standalone, both real image architectures and an independently installed exact Edge candidate. |

Continue completion, material review, performer selection, points and task creation
through the existing Domus task journey.

## 5. Current versus proposed product journey

A user opens the Domus task list in Home Assistant to see current open work.
Its displayed task state identifies available, assigned, in-progress, blocked or
draft work. They continue task management in Domus.

## 6. Functional behavior and state model

Page the existing open-only occurrence selection in stable occurrence order using
its supported 101-record queries and occurrence cursor inside one read transaction. A
completed occurrence leaves this open list, and reopening it restores the same
item identity. Two occurrences with the same title have different opaque
identities. Title or state changes keep the identity. Bound a complete snapshot
to 1,000 open occurrences, returning unavailable above the bound. A successful
empty read is zero. Failure hides previously read items and marks unavailable.

## 7. User-facing configuration

Provide a separate optional digest in Supervisor and standalone and a dedicated
task list choice in the companion. Explain that Home Assistant entity viewers
can see the titles and current states of all open household occurrences. Document
scope, connection, restart, rotation and revocation.

## 8. Clean Architecture design

An application-owned installation projection uses the existing task repository
query inside one scoped read transaction. Transport and companion adapters map
the bounded read. Domain commands retain responsibility for every write. Reuse
the existing private listener, secure standalone boundary and companion lifecycle.

## 9. UI/UX and content contract

Use English and Spanish names and state labels with plain text titles. The
entity advertises `supported_features = 0`. Empty, unavailable and recovered
reads remain distinguishable. Link the guide to the supported Domus task journey.
Keep focus, touch targets and recoverable request state in the existing app.

## 10. Failure, recovery, and cleanup

Missing, revoked, foreign, malformed or oversized reads hide all cached item
details. A later complete authorized read restores the same entity. Reconfigure
preserves the source identity across credential rotation. Unload cancels refreshes.
Remove only the disposable Core entries and the temporary Edge app and source.

## 11. Security, permissions, and privacy

The technical grant authorizes this task projection for one installation and
channel. It cannot act as a member or authorize writes. Other projection purposes
stay independent. Publish only title, current state and opaque item identity, and
keep credentials and source records out of logs and entity attributes.

## 12. Observability and operational UX

Home Assistant reports unavailable when a complete read fails. Keep safe bounded
errors and a one-minute refresh cadence. Document how to restore a revoked
connection and where to manage tasks.

## 13. Compatibility, migration, rollout, and rollback

Load saved companion entries and validate their existing purpose grants. Task
projection is disabled by default and uses SQLite schema 34. Pin the Edge runtime,
archive and installed files. Stable publication and deployment have separate gates.

## 14. Testing strategy and numeric budget

| Area | Minimum distinct cases | Behaviors/risks covered |
| --- | --- | --- |
| Authoritative tasks | 2 | Existing open selection, occurrence identity and complete bounded results |
| Authority and privacy | 2 | Separate grant, no private fields and no writes |
| Native integration | 2 | Read-only native list, localization, denial, recovery, rotation and restart |
| Deployment | 1 | Both protected compositions, real image architectures and installed Edge |
| Total | 7 | Distinct observable scenarios |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| ha-open-tasks-C01 | Authoritative tasks | ha-open-tasks-R01 | Compare every open state, duplicate titles, completed/cancelled/skipped exclusions, title edits and reopened identity with the existing occurrence records. |
| ha-open-tasks-C02 | Authoritative tasks | ha-open-tasks-R01 | Return all open occurrences beyond 25, across the 101/102 page boundary and at exactly 1,000, and fail unavailable on 1,001 without a partial native count. |
| ha-open-tasks-C03 | Authority and privacy | ha-open-tasks-R02 | Default-disabled, missing, rotated, foreign, cross-channel and wrong-purpose credentials cannot read task titles. Existing projections remain independent. |
| ha-open-tasks-C04 | Authority and privacy | ha-open-tasks-R02 | Only display fields and opaque identities appear, and repeated reads preserve all persisted facts. Native operations cannot write task or downstream state. |
| ha-open-tasks-C05 | Native integration | ha-open-tasks-R03 | Core resolves stable distinct entities and occurrence identities through title/state changes, rotation and process restart, with English and Spanish state labels. |
| ha-open-tasks-C06 | Native integration | ha-open-tasks-R03 | Core distinguishes empty, malformed, denied and recovered reads, clears previous items after denial and advertises no mutation features. |
| ha-open-tasks-C07 | Deployment | ha-open-tasks-R04 | Verify packaged Ingress and HTTPS standalone, real amd64 and ARM64 CI, and separately installed Edge synthetic bilingual task journeys and cleanup. |

## 15. Documentation and discoverability

| Path | Change |
| --- | --- |
| specs/home-assistant-todo-list.md | create |
| specs/home-assistant-surface.md | update |
| docs/contracts/home-assistant.md | update |
| docs/roadmap.md | update |
| docs/installation-home-assistant.md | update |
| docs/evidence/ha-open-tasks-qualification.md | create |

## 16. Acceptance scenarios

Execute the seven distinct cases and preserve existing companion coverage. Record
exact source, image architectures, installed candidate and scoped cleanup in the
PR. Verify completed work continues through Domus with its existing rules.

## 17. Requirements traceability

| Requirement | Cases |
| --- | --- |
| ha-open-tasks-R01 | ha-open-tasks-C01, ha-open-tasks-C02 |
| ha-open-tasks-R02 | ha-open-tasks-C03, ha-open-tasks-C04 |
| ha-open-tasks-R03 | ha-open-tasks-C05, ha-open-tasks-C06 |
| ha-open-tasks-R04 | ha-open-tasks-C07 |

## 18. Implementation sequence

Reuse the authoritative open-only query and project a bounded snapshot. Attach
the independent route and disabled-by-default digest. Add the native list,
lifecycle and localized state display. Verify contracts, package the exact Edge
candidate, qualify deployments and record installed evidence before merging.

## 19. Definition of Done

- [ ] The seven cases pass and each requirement has concrete evidence.
- [ ] Preserve full coverage per authored module and existing companion entries.
- [ ] Both actual architectures and protected compositions pass.
- [ ] The exact installed Edge candidate and scoped cleanup are recorded.
- [ ] Product checks, review and Branch Sync pass at the final PR head.

## 20. References and decisions

- The retained Home Assistant surface specification and contract own this projection.
- Open selection reuses the existing task repository filter.
- Build the bounded list from a consistent read transaction in schema 34.
