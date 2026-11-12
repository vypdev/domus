# Expose task deadline counts as native Home Assistant sensors

- Status: Draft
- Catalog capability: home-assistant-surface

## 1. Executive summary

Add an opt-in pair of native, read-only Home Assistant sensors for open Domus tasks due today and open overdue tasks. Both counts come from the same authoritative deadline classification as Overview, and the groups remain disjoint. A successful empty result displays zero; a failed or untrusted result displays unavailable. A dedicated count-only grant, bounded coordinated refresh, and stable identity protect the projection. This companion adds only the deadline sensors; the existing Home Assistant surface and calendar contracts and cases remain in force.

```text
Operator enables the count-only grant -> Home Assistant registers both sensors -> Domus returns both counts together -> Home Assistant displays counts or unavailable and retries within bounds
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Home Assistant users need authoritative due-today and overdue counts for dashboards and automation conditions. Counting calendar events or one page of tasks can omit overdue work and cannot guarantee Domus deadline semantics. A zero must mean Domus returned a successful empty result, not that the source, authorization, or projection failed.

### 2.2 Current behavior

The retained owner, `specs/home-assistant-surface.md`, defines the broader Home Assistant integration contract and proposed task entities; the calendar companion, `specs/home-assistant-calendar.md`, defines a separate planned/due event projection. Neither contract supplies these authoritative count sensor states. Overview already groups deadlines: `backend/src/domus/application/task_queries.py`, `_overview_deadline_groups`, compares timed deadlines with the observation instant and date-only deadlines using the saved schedule policy. `docs/evidence/overview-deadlines-qualification.md` records qualification for timed boundaries, fixed and relative date-only policies, totals, and malformed or partial projections. These are the source semantics this delta preserves; they do not establish sensor implementation or acceptance.

### 2.3 Evidence

- `specs/home-assistant-surface.md` is the retained owning contract; `specs/home-assistant-calendar.md` owns the separate native calendar increment. Their existing requirements and cases remain unchanged.
- `backend/src/domus/application/task_queries.py`, `_overview_deadline_groups`, is the observed Overview classifier. `docs/evidence/overview-deadlines-qualification.md` identifies its qualification evidence and boundaries.
- The selected source does not establish native deadline sensor acceptance. Core 2026.10.4 testing, both deployment compositions, the authorized Chrome journey, and English and Spanish setup and recovery guidance remain prospective acceptance outcomes.
- The exact implementation route, response schema, and concrete project verification invocation for this new projection remain unverified; no implementation command is asserted here.

## 3. Actors, surfaces, and terminology

The Domus operator opts in and configures the dedicated count-only installation grant. The Home Assistant administrator configures the endpoint and grant in Core. Dashboard viewers and automations consume two read-only native sensor states. Domus remains authoritative for task state and deadline classification; Home Assistant receives counts only.

“Due today” and “overdue” use the existing Overview deadline rules for open work, including exact timed deadlines, fixed and relative date-only schedules, household day boundaries, and open occurrence states. “Unavailable” means the affected projection cannot provide a trustworthy count. A successful empty snapshot is available with count zero. “Source identity” means installation UUID plus channel; sensor unique identities are bound to that identity and remain stable through entity rename, restart, and grant rotation.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

1. Expose disjoint due-today and overdue counts that match the Overview classifier for open tasks.
2. Distinguish successful zero from absent household, unreachable source, revoked grant, or malformed data; recover with the same entities.
3. Preserve stable, unique sensor identities bound to installation and channel through rename, restart, and grant rotation.
4. Require opt-in dedicated count-only access, isolate it from calendar and human credentials across private Supervisor-network and standalone HTTPS access, and stop access when disabled or revoked.
5. Return both nonnegative integer counts together in a fixed response without task records, titles, assignees, or identifiers; bound polling and failures, coordinate one refresh per connection, and stop refreshes on unload.
6. Preserve the existing native calendar entry, credentials, event queries, and entity identities when calendar and sensors are configured together.
7. Validate both deployment compositions with pinned Core 2026.10.4 and provide English and Spanish setup and recovery guidance.

### 4.2 Non-goals

This delta does not change the retained Home Assistant surface or native calendar contracts, add mutation services or Domus rule execution, use calendar event counts as deadline counts, expose task records through the sensor response, or require a Gateway dependency.

### 4.3 Fixed product and safety invariants

- Domus Overview deadline classification is authoritative; both groups are disjoint and include only open work. Do not substitute a calendar window or partial task page.
- A successful empty read is zero. Missing household, source failure, revoked or invalid grant, and malformed data produce unavailable for affected sensors, never a fabricated zero; recovery restores the same entities.
- Access is opt-in and uses a dedicated count-only grant bound to installation and channel. Keep its credential material separate from calendar-only and human credentials; store only the grant digest in Domus. The private Supervisor-network route and standalone HTTPS route enforce the same grant. Rotation rejects retired credentials while preserving sensor identity; disablement or revocation stops access.
- Each bounded refresh returns both counts together and contains no task-level data. One coordinator per connection prevents duplicate refreshes, and unload stops refresh activity.
- Configure sensors alongside the calendar without changing its entry, credentials, event queries, or entity identities. Core 2026.10.4 and both deployment compositions are the acceptance target; this target is not evidence that acceptance has occurred.
- Publication DoD must observe that the specification satisfies the required format, internal and cross-document consistency is checked, and reciprocal catalog ownership, paths, and evidence agree with the generated view.

| Requirement | Behavior |
| --- | --- |
| SDD-I112-U1-R1 | Classify open tasks with the Overview deadline rules and expose disjoint counts for tasks due today and overdue. |
| SDD-I112-U1-R2 | Report zero for a successful empty result; report affected sensors unavailable for missing household, unreachable source, revoked grant, or malformed data, and restore the same entities after recovery. |
| SDD-I112-U1-R3 | Give both sensors stable unique identities bound to installation and channel, preserved across rename, restart, and grant rotation. |
| SDD-I112-U1-R4 | Require an opt-in dedicated count-only grant bound to installation and channel; isolate it from calendar and human credentials across Supervisor-network and standalone HTTPS access, and stop access when revoked or disabled. |
| SDD-I112-U1-R5 | Return both nonnegative integer counts together in a fixed response without task records, titles, assignees, or identifiers; bound polling and failures, coordinate one refresh per connection, and stop refreshes on unload. |
| SDD-I112-U1-R6 | Preserve the existing native calendar entry, credentials, event queries, and entity identities when sensors and calendar are configured together. |
| SDD-I112-U1-R7 | Support both deployment compositions with pinned Core 2026.10.4 and provide English and Spanish setup and recovery guidance. |

## 5. Current versus proposed product journey

This companion adds the native deadline-count sensor journey while retaining the existing `specs/home-assistant-surface.md` contract and `specs/home-assistant-calendar.md` cases and behavior. The existing Overview computes due-today and overdue groups, and the calendar projection publishes bounded calendar events; neither supplies these native sensor states. The calendar range and event contract is not a substitute for counting every open overdue occurrence.

An operator explicitly opts in by configuring a dedicated count-only installation grant for the installation UUID and channel, then adds the Domus sensor integration in Home Assistant. Both sensors read one authoritative Domus snapshot. A successful empty snapshot displays zero; failed or unauthorized reads make affected sensors unavailable until recovery, preserving entity identity. Operators can use the counts on dashboards or as automation conditions. Calendar setup, credentials, event queries, and entity identity continue to work when configured alongside the sensors.

## 6. Functional behavior and state model

The integration exposes two read-only sensors: open tasks due today and open overdue tasks. Counts use the same Overview deadline classification, household day boundary, and open occurrence states. Timed deadlines and fixed or relative date-only schedules follow the Overview rules; the groups are disjoint, so an occurrence is never counted in both. The authoritative classifier is implemented in `backend/src/domus/application/task_queries.py` by `_overview_deadline_groups`; date-only qualification uses `_date_only_deadline` in that file. The Overview qualification evidence in `docs/evidence/overview-deadlines-qualification.md` records boundary and schedule-policy coverage. The companion acceptance must compare both counts with that classifier across deadline and day boundaries (domus-ha-deadline-sensors-C01).

Fetch both nonnegative integer counts together in one fixed-size response. The response contains no task records, titles, assignees, or identifiers. Coordinate refreshes so each connection has at most one active refresh; bound polling, timeouts, and failures, and cancel scheduled work and listeners on unload. A successful empty snapshot is available with value zero. Missing household, unreachable source, revoked grant, malformed data, or other failed read makes the affected sensors unavailable; never translate failure or partial data into zero. Retry through normal bounded polling, then restore the same entities on recovery (domus-ha-deadline-sensors-C02, domus-ha-deadline-sensors-C06).

Sensor unique IDs are stable, unique, and bound to installation and channel, independent of the editable Home Assistant entity name. Rename, restart, and same-source grant rotation preserve those identities; a different installation or channel produces distinct identities. Rotation retires the old grant, while disabling or revoking the grant stops sensor access (domus-ha-deadline-sensors-C03, domus-ha-deadline-sensors-C05). With both projections configured, the existing calendar entry, credentials, event queries, and entity identities remain functional (domus-ha-deadline-sensors-C07).

## 7. User-facing configuration

Setup is explicit and opt-in. The operator configures a dedicated count-only grant bound to the Domus installation UUID and channel and supplies its endpoint and bearer through Home Assistant's native setup flow. Store only the grant digest in Domus. Keep this grant separate from calendar-only credentials and human credentials. Enforce the same grant scope over the private Supervisor-network route and standalone HTTPS; standalone access requires HTTPS. Do not accept calendar credentials, human authentication, unsupported methods, wrong-scope or retired grants as count authorization, and do not return count data for denied access (domus-ha-deadline-sensors-C04).

Allow same-source reconfiguration and grant rotation without changing sensor identities. Revoke access by disabling/removing the dedicated grant; the old grant must cease to work. Setup and recovery instructions must be available in English and Spanish, including unavailable-state troubleshooting and reconnection steps (domus-ha-deadline-sensors-C05, domus-ha-deadline-sensors-C08). Preserve the existing calendar configuration and credential lifecycle when both features are enabled (domus-ha-deadline-sensors-C07).

## 8. Clean Architecture design

Keep deadline classification in the existing Domus application query and treat Home Assistant as a bounded projection. The current `_overview_deadline_groups` classifier resides in `backend/src/domus/application/task_queries.py`; the existing `backend/src/domus/application/ha_calendar_projection.py` formats calendar facts and is not evidence of a deadline-count projection. The selected source confirms the calendar composition in `backend/src/domus/composition/ha_calendar.py`; these existing calendar files and behaviors remain owned by `specs/home-assistant-calendar.md`.

The new sensor path should use a dedicated installation-scoped count query and boundary, with explicit composition for both Supervisor-network and standalone HTTPS deployments. Keep transport credential verification and response mapping in adapters, wiring in composition, and classification in the application/domain boundary; do not put deadline policy in Home Assistant or derive totals from calendar pages. Return both counts as a fixed projection, enforce scope and bounds before exposing data, and map authorization, transport, and malformed-response failures to unavailable without leaking credentials or task details. Coordinate one refresh per connection and cancel it on unload.

Validate actual entity registration, stable identity, classifier parity, zero versus unavailable and recovery, access isolation, fixed response shape, bounded polling and failure behavior, calendar coexistence, and unload in disposable Home Assistant Core 2026.10.4 environments for both compositions. Validate the exact Domus Edge candidate in the authorized Chrome journey and provide English and Spanish setup and recovery guidance. The selected compatibility matrix, `docs/compatibility-home-assistant.md`, lists Core 2026.10.4 as a reference and does not establish acceptance for this sensor increment; the concrete acceptance invocation and prerequisite remain unverified.

## 9. UI/UX and content contract

### 9.1 Sensor presentation

Register two native read-only sensors: tasks due today and open overdue tasks. Their visible state is a nonnegative integer when the read succeeds; show unavailable when the relevant projection cannot be read. A successful empty result is `0`, never unavailable. Give each sensor an accessible name that distinguishes the deadline group, and do not rely on color or an icon to convey its meaning. Home Assistant dashboards and automation conditions may consume the counts; task details remain in Domus.

The due-today and overdue groups MUST remain disjoint and use the same authoritative deadline classification as Overview, including exact timed deadlines, fixed and relative date-only policies, household day boundaries, and open occurrence states. The Overview qualification in `docs/evidence/overview-deadlines-qualification.md` records the classification boundaries and existing evidence; it does not establish sensor integration acceptance. Keep sensor state limited to the count, without task attributes. English and Spanish setup and recovery guidance MUST use the project’s supported locale behavior; the concrete integration translation and fallback behavior remains to be specified and verified.

## 10. Failure, recovery, and cleanup

### 10.1 Failure and recovery

| Condition | Visible result | Recovery |
|---|---|---|
| Successful snapshot with no matching tasks | `0` for the corresponding sensor | Normal bounded refresh |
| Household missing, source unreachable, grant revoked, or malformed count response | Affected sensors unavailable; never convert a failed or partial response to zero | Restore the household/source or configure a valid grant; retry on a later bounded refresh |
| Source recovers | The same sensor entities return to available counts | Preserve entity identity through recovery |
| Integration entry unloads | No further scheduled or in-flight refresh is allowed to publish state | Cancel scheduled work and detach listeners/coordinator resources |

Errors MUST state the impact, safe cause, action, and retained state in that order. Polling and timeout limits, retry policy, and treatment of a partial two-count result need explicit implementation values; the issue requires both counts to be read together and bounded failures. Retain no task records in this projection. Recovery behavior is covered by the companion acceptance inventory.

## 11. Security, permissions, and privacy

### 11.1 Permissions and data handling

Setup MUST be opt-in and use a dedicated count-only grant bound to the Domus installation UUID and channel. Domus stores only the grant digest. Keep this grant separate from calendar-only credentials, human sessions, and Supervisor credentials. Both the private Supervisor-network route and standalone HTTPS route MUST enforce the same scope and reveal no count data for a wrong scope, retired grant, calendar credential, human authentication, or unsupported method. Standalone access requires HTTPS; the Supervisor route remains private and unpublished, preserving the existing Ingress and human-session boundary described in `specs/home-assistant-surface.md`.

The response MUST contain exactly the two nonnegative integer counts in a fixed bounded shape, with no task records, titles, assignees, or identifiers. Do not put grant values, task data, or complete credential-bearing URLs in logs or diagnostics. Rotation MUST reject the retired grant while preserving sensor identities; disabling or revoking the grant MUST stop access. The native calendar’s existing entry, credentials, event queries, and entity identities remain compatible when both projections are configured, as required by the retained calendar contract in `specs/home-assistant-calendar.md`.

## 12. Observability and operational UX

### 12.1 Status and operator evidence

Home Assistant state is the operator-facing signal: a numeric value means the count read succeeded, while unavailable means the projection could not be trusted. Never display stale or partial data as a current count or collapse authorization failure, malformed data, and source unavailability into zero. Provide sanitized diagnostic categories sufficient to distinguish missing household, unreachable source, revoked or invalid grant, malformed response, timeout, and unload. Diagnostics MUST omit grant material and task content; no telemetry leaves the installation by default under `specs/home-assistant-surface.md`.

Coordinate one refresh for both sensors per connection, bound polling and failures, and stop refresh work on unload. The selected `custom_components/domus_calendar/manifest.json` identifies the existing calendar integration package as local polling; it does not establish a sensor implementation or sensor polling limits. Exact timeout, polling interval, and safe diagnostic fields remain implementation decisions to verify.

## 13. Compatibility, migration, rollout, and rollback

### 13.1 Compatibility and rollout

Qualify both Supervisor-network and standalone HTTPS deployment compositions with disposable Home Assistant Core 2026.10.4. The pinned target is a required acceptance exercise, not evidence that acceptance has already passed; later Core versions require separate qualification without imposing a runtime version ceiling. Validate the exact Domus Edge candidate in the authorized Chrome journey, and provide English and Spanish setup and recovery guidance.

Adding sensors MUST preserve the existing native calendar entry, its credentials, event queries, and entity identities when both are configured. Sensor identities MUST be unique and bound to installation and channel, surviving rename, restart, grant rotation, and recovery; a different installation or channel is distinct. Reconfiguring or rotating the dedicated grant must not require replacing those identities. Revocation or disabling removes sensor access, and unloading stops refreshes. The selected tree contains the calendar manifest at `custom_components/domus_calendar/manifest.json`; its presence is not evidence of the proposed sensor entities or acceptance. No broader release or deployment outcome is claimed by this companion delta.

## 14. Testing strategy and numeric budget

Minimum: eight distinct cases, one for each companion acceptance scenario. The budget is a floor and does not establish completeness or executed acceptance. Allocate coverage across domain classification and date boundaries; availability, recovery and entity state; Home Assistant registration and lifecycle; grant security and deployment composition; bounded projection and calendar compatibility; and setup, localization and operator recovery guidance. Count each distinct inventory case once. Use deterministic clocks, source and network fakes for unit and contract coverage; use disposable Home Assistant Core 2026.10.4 environments for integration coverage of both Supervisor-network and standalone HTTPS compositions. Verify the exact Domus Edge candidate in the authorized Chrome journey, alongside English and Spanish setup and recovery content. Assertions must check semantic results and side effects, including no task data in the count response, no access after revocation or unload, and preservation of existing calendar behavior. Retain the owning surface's global and changed-module quality gates; this companion does not claim their execution.

The deadline baseline is evidenced by `tests/backend/test_task_overview.py` and `docs/evidence/overview-deadlines-qualification.md`. Those sources establish Overview behavior, not native sensor acceptance. This selected tree declares pnpm 10.34.0 and Node >=24.20.0 <25 in `package.json`; the README's `pnpm run validate:specifications` and `pnpm run generate:specifications` invocations are not declared there. A concrete SDD/catalog validation invocation and prerequisite remain unverified. Publication requires an observable outcome that this specification satisfies the required format; internal and cross-document consistency is checked; and reciprocal catalog ownership, paths and evidence agree with the generated view. These are publication constraints, not product tests or evidence that any check has run.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| deadline classification | 1 | Observable scenarios in the case inventory. |
| availability and recovery | 1 | Observable scenarios in the case inventory. |
| entity identity | 1 | Observable scenarios in the case inventory. |
| access isolation | 1 | Observable scenarios in the case inventory. |
| grant rotation and revocation | 1 | Observable scenarios in the case inventory. |
| projection and unload | 1 | Observable scenarios in the case inventory. |
| calendar compatibility | 1 | Observable scenarios in the case inventory. |
| deployment and guidance | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| domus-ha-deadline-sensors-C01 | deadline classification | SDD-I112-U1-R1 | Compare both exact counts with the Overview classifier for open timed, fixed date-only, and relative date-only work across day and deadline boundaries; verify the groups are disjoint. |
| domus-ha-deadline-sensors-C02 | availability and recovery | SDD-I112-U1-R2 | Observe zero for a successful empty snapshot and unavailable for absent household, unreachable source, revoked grant, and malformed data; verify recovery restores the same entities. |
| domus-ha-deadline-sensors-C03 | entity identity | SDD-I112-U1-R3 | Register both sensors in disposable Core with stable unique identities bound to installation and channel; verify rename and restart preserve identity and a different installation or channel is distinct. |
| domus-ha-deadline-sensors-C04 | access isolation | SDD-I112-U1-R4 | Verify private Supervisor and standalone HTTPS access isolation; wrong scope, retired credentials, calendar credentials, human authentication, and unsupported methods yield no count data. |
| domus-ha-deadline-sensors-C05 | grant rotation and revocation | SDD-I112-U1-R3, SDD-I112-U1-R4 | Rotate and reconfigure the dedicated grant for the same installation; reject the retired grant, preserve entity IDs, and remove sensor access when the grant is disabled. |
| domus-ha-deadline-sensors-C06 | projection and unload | SDD-I112-U1-R5 | Verify one coordinated read of both fixed-size counts, bounded failures and polling, no task data in the response, and no refreshes after unload. |
| domus-ha-deadline-sensors-C07 | calendar compatibility | SDD-I112-U1-R6 | Keep the existing calendar entry, credentials, event queries, and identities functional while both sensor and calendar projections are configured. |
| domus-ha-deadline-sensors-C08 | deployment and guidance | SDD-I112-U1-R7 | Validate both deployment compositions against pinned Core 2026.10.4, the exact Domus Edge candidate in the authorized Chrome journey, and English and Spanish setup and recovery guidance. |

## 15. Documentation and discoverability

Provide Home Assistant operator guidance in English and Spanish for enabling the opt-in count-only grant, configuring the two sensors in either deployment composition, understanding zero versus unavailable, recovering from source or credential failure, rotating or disabling the grant, and unloading the integration. Explain that both counts use Domus Overview deadline semantics and are not inferred from calendar windows or a page of task records. Document that the fixed response contains only the two nonnegative counts, that both entities refresh together with bounded polling, and that the existing calendar configuration and identities remain supported. Include accessible sensor names and state descriptions, setup prerequisites, credential separation, troubleshooting actions, and the expected stable identity behavior across rename, restart and grant rotation. Cross-reference the retained contracts in `specs/home-assistant-surface.md` and `specs/home-assistant-calendar.md`, and the Overview evidence in `docs/evidence/overview-deadlines-qualification.md`. The companion document is a prospective create declaration, not an existing file. The concrete invocation and prerequisite for specification/catalog format, consistency and generated-view checks remain unverified; a documentation-link check alone does not establish those outcomes.

| Path | Change |
| --- | --- |
| specs/home-assistant-deadline-sensors.md | create |

[specs/home-assistant-deadline-sensors.md](home-assistant-deadline-sensors.md)

## 16. Acceptance scenarios

The eight distinct scenarios in the companion inventory define acceptance and require observable state and side-effect assertions. Compare due-today and overdue counts against the Overview classifier for open timed, fixed date-only and relative date-only work across day and deadline boundaries, confirming the groups are disjoint. Confirm a successful empty snapshot reports zero, while absent household, unreachable source, revoked grant and malformed data make affected sensors unavailable; recovery restores the same entities. In disposable Core, verify stable unique identities bound to installation and channel across rename and restart, and distinct identities for another installation or channel. Exercise private Supervisor and standalone HTTPS isolation: wrong scope, retired and calendar credentials, human authentication and unsupported methods return no count data. Rotate and reconfigure the dedicated grant, reject the retired credential, preserve entity IDs, and remove sensor access when disabled. Confirm one coordinated fixed-size read returns both counts, has bounded polling and failures, excludes task records and stops refresh after unload. With sensors and calendar configured together, verify the existing calendar entry, credentials, event queries and entity identities still work. Validate both deployment compositions on pinned Core 2026.10.4, verify the exact Domus Edge candidate in the authorized Chrome journey, and inspect English and Spanish setup and recovery guidance. Live acceptance remains pending until these artifacts are exercised; the specified target is not evidence of a passing result.

## 17. Requirements traceability

The requirement-to-case mapping is reciprocal with the eight companion inventory definitions. `SDD-I112-U1-R1` is exercised by `domus-ha-deadline-sensors-C01`, which compares exact disjoint counts against Overview deadline classification. `SDD-I112-U1-R2` is exercised by `domus-ha-deadline-sensors-C02`, which checks empty success, each unavailable condition, and recovery of the same entities. `SDD-I112-U1-R3` is exercised by `domus-ha-deadline-sensors-C03` and `domus-ha-deadline-sensors-C05`, covering identity across rename, restart and grant rotation, plus installation/channel uniqueness. `SDD-I112-U1-R4` is exercised by `domus-ha-deadline-sensors-C04` and `domus-ha-deadline-sensors-C05`, covering route and credential isolation, rotation, revocation and disabled access. `SDD-I112-U1-R5` is exercised by `domus-ha-deadline-sensors-C06`, covering the fixed count-only response, coordinated bounded refresh and unload. `SDD-I112-U1-R6` is exercised by `domus-ha-deadline-sensors-C07`, which verifies existing calendar behavior when both projections are configured. `SDD-I112-U1-R7` is exercised by `domus-ha-deadline-sensors-C08`, which covers both deployments, pinned Core, the authorized Chrome journey, and English and Spanish guidance.

Publication also requires the specification to satisfy the required format, internal and cross-document consistency to be checked, and reciprocal catalog ownership, paths and evidence to agree with the generated view. A concrete invocation and prerequisite for those specification/catalog outcomes remain unverified; no documentation check substitutes for them. These publication constraints are not product requirements or additional cases. The owning case identities in `specs/home-assistant-surface.md` and `specs/home-assistant-calendar.md` remain references and are not copied or renamed into this companion inventory.

| Requirement | Cases |
|---|---|
| SDD-I112-U1-R1 | domus-ha-deadline-sensors-C01 |
| SDD-I112-U1-R2 | domus-ha-deadline-sensors-C02 |
| SDD-I112-U1-R3 | domus-ha-deadline-sensors-C03, domus-ha-deadline-sensors-C05 |
| SDD-I112-U1-R4 | domus-ha-deadline-sensors-C04, domus-ha-deadline-sensors-C05 |
| SDD-I112-U1-R5 | domus-ha-deadline-sensors-C06 |
| SDD-I112-U1-R6 | domus-ha-deadline-sensors-C07 |
| SDD-I112-U1-R7 | domus-ha-deadline-sensors-C08 |

## 18. Implementation sequence

Implement the authoritative count query from the existing Overview deadline policy, then expose one fixed-size count-only projection containing both nonnegative integer values. Add the dedicated opt-in grant bound to installation and channel, storing only its digest; enforce equivalent isolation for the private Supervisor-network route and standalone HTTPS. Build the native Home Assistant sensors with stable installation-and-channel identities, coordinated bounded refresh, unavailable handling, recovery, and unload cleanup. Preserve the native calendar entry, credentials, queries, and entity identities when both projections are enabled. Qualify both deployment compositions on disposable Home Assistant Core 2026.10.4, and provide English and Spanish setup and recovery guidance. Compare classification to the Overview contract and evidence in `docs/evidence/overview-deadlines-qualification.md`; its cases document timed boundaries, household-day handling for date-only deadlines, exact totals, and unavailable behavior. The immutable owner `specs/home-assistant-surface.md` remains authoritative for its existing contract and cases; `specs/home-assistant-calendar.md` remains authoritative for the calendar increment. The target companion `specs/home-assistant-deadline-sensors.md` is a prospective create declaration, not an existing file.

## 19. Definition of Done

The eight distinct companion acceptance cases in the inventory must pass and remain mapped reciprocally to the seven requirements: exact disjoint counts against Overview classification; empty success versus unavailable conditions and recovery; stable sensor identity; access isolation; grant rotation and revocation; fixed count-only responses, bounded coordinated polling, and unload; calendar compatibility; and both deployment compositions with localized setup and recovery guidance. These are required future acceptance outcomes, not evidence that implementation or tests already exist. Verify the projection never returns task records, titles, assignees, or identifiers; malformed or failed reads never appear as zero; grant revocation removes access; and recovery retains the same entities. Preserve the immutable Home Assistant surface and calendar owners and their case identities. Exercise actual sensor registration and lifecycle on disposable Core 2026.10.4 for both compositions, and provide the specified authorized Chrome journey for the exact Domus Edge candidate, with cleanup evidence. Later Core versions require separate qualification; do not impose a runtime version ceiling.

Before publication, the specification satisfies the required format; internal and cross-document consistency is checked; reciprocal catalog ownership, paths, and evidence agree with the generated view. These are observable publication outcomes, not proof of semantic completeness or executed acceptance. The repository standard in `specs/README.md` recommends `pnpm run validate:specifications` and `pnpm run generate:specifications`; the root `package.json` declares pnpm 10.34.0 but does not define those scripts. Their concrete invocation and prerequisites therefore remain unverified; do not treat those unavailable examples as required steps or as passing validation. No verification is claimed by this draft. No release, live installation, deployment, or promotion is authorized.

## 20. References and decisions

This is a bounded companion to the retained owner `specs/home-assistant-surface.md`; it adds deadline-count sensors only and leaves that owner and its cases intact. The native calendar companion `specs/home-assistant-calendar.md` remains in force, including its existing entry, credentials, event queries, and entity identity. The Overview deadline rules are the source of classification; `docs/evidence/overview-deadlines-qualification.md` records the existing qualification evidence but does not establish acceptance of the proposed sensors. Issue #112 requests two native read-only counts, a dedicated count-only grant, consistent Supervisor-network and standalone HTTPS access, and pinned Core 2026.10.4 qualification. The selected compatibility reference `docs/compatibility-home-assistant.md` does not itself establish acceptance for this increment. The concrete publication validation invocation and prerequisites remain unverified as stated in section 19.
