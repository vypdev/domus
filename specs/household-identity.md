# Household members, Home Assistant identity and permissions

- Status: Draft
- Date: 2026-10-28
- Catalog capability ID: household-identity
- Last verified: 2026-10-31 (document structure only; no implementation evidence)
- Owners: Domus maintainer; engineering/product reviewers to be assigned
- Scope: Each participating person uses their own Home Assistant account. Domus associates that verified user with one household member and applies explicit backend permissions independently of an optional person entity.
- Related issues/PRs: https://github.com/vypdev/domus/issues/2
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: Detailed permission matrix/override review; authenticated recovery after external HA account loss; proof of HA identity/administrator status in both deployment targets; technical service principal policy. The owner confirmed three administrator-mapping modes with all HA administrators as the default, plus configurable household profiles and per-member permission exceptions. Catalog gate prerequisites remain unverified.

## 1. Executive summary

Each participating person uses their own Home Assistant account. Domus associates that verified user with one household member and applies explicit backend permissions independently of an optional person entity.

```text
Authenticated member -> validated domain command -> durable result -> household and HA projections
```

This is a prospective Draft, not an implemented or accepted capability. The first usable release covers all domains and both deployment targets.

## 2. Problem, current behavior, and evidence

HA users and person entities have different meanings. The owner confirmed individual HA accounts for every participant; a shared adult identity or independent Domus PIN would contradict that requirement.

At the original documentation baseline on 2026-10-28, these domain workflows had no implementation. The merged M1 identity/storage foundation now has separate backend evidence. The task approval and material-authority additions in this review remain prospective; this documentation change adds no runtime behavior.

Evidence: the owner's attached brief and subsequent decisions in [product vision](../docs/product-vision.md), the pinned [reference investigation](../docs/reference-investigation.md), and the existing repository baseline. Retrospective classification is not applicable: no as-built product baseline is reconstructed.

## 3. Actors, surfaces, and terminology

Actors: Administrator; adult member; restricted member; read-only member; scoped automation principal.

Primary surfaces: application UI, HTTP domain boundary, relevant HA entities/services, activity and diagnostics. Definitions of member, principal, occurrence, demand and ledger are shared in the [glossary](../docs/glossary.md). The actor recording an action is distinct from its selected target and actual performer.

## 4. Goals, non-goals, and fixed invariants

Goals and fixed invariants are the following normative requirements. No configuration may weaken authorization, ledger integrity, attribution or idempotency.

| Requirement | Behavior |
|---|---|
| household-identity-R1 | Every participating member MUST map to a distinct verified HA user; person entities MUST NOT authenticate users. |
| household-identity-R2 | Permissions MUST be enforced in the backend for every read and mutation using predefined administrator, adult, restricted and viewer profiles, administrator-configurable household grants and explicit per-member exceptions, with deterministic precedence and current-policy checks. Task-specific material authority MUST remain bounded to validated linked usage and MUST NOT grant general stock access; an adult participation option MUST NOT make a restricted member an adult verifier. |
| household-identity-R3 | Suspension, role changes and unlinking MUST revoke effective access without erasing historical actor references. |
| household-identity-R4 | Identity flows MUST work in both deployment targets without trusting arbitrary client headers or exposing HA tokens to diagnostics. |
| household-identity-R5 | Administrators MUST retain control of configuring point values, verification, automation settings and privileged corrections; Domus authorization commands MUST preserve at least one active effective administrator. |
| household-identity-R6 | Members MUST control their locale and notification preferences and view participation without treating points as the sole fairness metric. |
| household-identity-R7 | Administrator mapping MUST support all_ha_administrators by default, setup_administrator and selected_ha_user alternatives, prove HA identity/administrator status where required and preserve last-administrator/recovery safety without granting privilege from browser arrival order or caller-supplied identity. |

Non-goals: changing Copilot, changing the existing gateway, building an MCP server, adding mandatory cloud/AI dependencies, or claiming production readiness from a document.

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User/operator effect |
|---|---|---|---|
| Enter | No Domus UI | Verified HA principal opens the relevant surface | Role and scope are explicit |
| Act | No domain command | Validate input, permission and current revision | Invalid data leaves the draft intact |
| Commit | No durable domain record | Store change and operation receipt atomically | Retry cannot duplicate effects |
| Observe | No projection | Show committed facts and pending downstream projections | Partial success remains understandable |

```mermaid
flowchart LR
    Entry[Authenticated entry] --> Validate[Authorize and validate]
    Validate --> Commit[Commit domain result]
    Commit --> View[Show facts and pending work]
```

Text equivalent: authenticated entry -> authorization and validation -> durable domain commit -> visible facts with any pending projection. Domain-specific alternatives are described below.

## 6. Functional behavior and state model

### 6.1 Domain model and normal path

Member(id, display_name, avatar_reference, ha_user_id, optional person_entity_id, role, active, preferences, revision). The HA user association is unique within the household. A person association supplies profile/presence only. Membership can be invited -> linked -> active -> suspended -> archived; unlinking immediately removes access without deleting historical authorship.

The owner confirmed predefined role profiles with administrator-adjustable household permissions and per-member exceptions. RoleProfile retains the base role, explicit grants/denials and version; a MemberPermissionOverride retains permission, allow/deny, actor, reason and revision. Within configurable permissions, an explicit member override takes precedence over the household profile, which takes precedence over the predefined default; contradictory entries at the same level are rejected, with denial as the safe result for unresolved conflicts. Identity, household scope, installation limits and domain invariants remain hard constraints. Granting one action to a restricted member does not make that performer an adult or bypass required adult verification. Only an authorized administrator edits this policy; ordinary members cannot edit their own authority. Changes invalidate effective-permission caches and are rechecked at command commit and protected-result lookup. Snapshotted policy revisions explain past operations but cannot authorize a revoked grant.

AdministratorMappingPolicy is configured explicitly during setup and may later be changed through an authorized audited command. The owner requested all three modes, with all_ha_administrators as the default. In that mode, each authenticated, authoritatively verified HA administrator receives the inherited Domus administrator role; other HA users do not. setup_administrator initially grants Domus administration only to the verified HA administrator who completes setup. selected_ha_user grants it initially to the explicitly selected active HA user, chosen by the verified HA administrator configuring the installation. Subsequent explicit Domus role assignments remain audited; alternate modes do not automatically elevate every other HA administrator. Continuous inheritance of current HA administrator status applies to all_ha_administrators; the alternatives designate the recorded setup identity or selected active HA account, and the selected account need not itself be an HA administrator.

Initial configuration requires an explicit setup action by a proven HA administrator. Merely loading the page does not create a household or grant privilege. The default mode may link/activate a proven HA administrator according to the selected mapping policy after setup; ordinary unlinked users still need authorized membership activation. An inherited administrator grant retains its HA source and is removed when that source is no longer valid or the mapping changes; any independent explicit grant is evaluated separately. A profile/member edit cannot silently demote a currently inherited administrator role: change the authorized mapping or its HA source. Mapping never bypasses suspension, known revocation or technical-principal boundaries. A transport credential, person entity or submitted is_admin flag is not proof of a human HA administrator.

The owner confirmed on 2026-10-29 that adult performers need no completion verification by default and restricted performers require approval by an authorized adult. Administrator control of verification configuration is separate from permission to approve a restricted member's completion. The effective policy follows actual performers; an adult submitting the record does not silently turn restricted work into adult work. Explicit overrides remain administrator-controlled and audited.

The owner-confirmed participation and material defaults are defined in [Tasks](household-tasks.md), including household policy, administrator-authorized task precedence and completion snapshots. An authorized adult performer may approve by default; a restricted member remains ineligible to approve. Current membership/permission checks still apply. The narrow material authority is only for reviewed usage of server-validated materials linked to a task the actor may complete; it never enables general inventory operations. Disabling that authority retains valid work and visibly unposted usage. The task acceptance inventory owns the distinct new policy scenarios; they are not counted again here. The identity permission enum and typed policy accept the task companion's additive read/claim/manage/on-behalf/scoped-material permissions; tested application helpers reread current membership and policy. Transactional task commands, task HTTP and material settlement remain pending, so permission support alone does not establish their acceptance.

### 6.2 States and alternatives

Ordinary unlinked membership cannot participate; linked accounts become active after administrator assignment, with verified administrator mapping as the explicit exception above. Suspended users retain historical attribution but cannot access protected reads or commands. Domus role, profile, mapping and suspension commands cannot remove the last active effective administrator. HA can independently revoke or remove accounts; Domus must then remove invalid inherited access and surface authenticated recovery rather than keep stale privilege or give the next arbitrary browser administration. The supported recovery procedure remains an engineering/security gate.

Authorization applies to operation lookup and duplicate receipts as well as new writes. Replaying a once-authorized command does not bypass a later suspension or expose the old private result to another principal. Household role revocation is checked against current local authority before returning protected data; a snapshotted execution policy is not a permission grant. Implementing the selected initial administrator mapping and recovery after external HA account loss requires a reviewed authenticated procedure; never promote the first arbitrary browser session or silently substitute a shared administrator.

A duplicate uses its original operation receipt. A changed payload under the same key is a conflict. Out-of-order events use aggregate revision and source identity. Cancellation never erases an already committed ledger effect; compensation is explicit.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| `default_member_role` | enum | restricted | adult, restricted or viewer for ordinary activation; verified administrator mapping is a separate explicit policy | household; assigned at activation |
| `administrator_mapping` | enum | all_ha_administrators | all_ha_administrators, setup_administrator, selected_ha_user; selected mode requires a verified active target | installation/household; versioned, audited; current HA source checked |
| `role_permissions` | typed permission map | predefined administrator/adult/restricted/viewer profiles | supported explicit allow/deny entries; administrator-controlled, cannot weaken hard constraints | household profile revision |
| `member_permission_overrides` | typed permission map | none | supported explicit per-member exceptions; current administrator authorization and audit required | member policy revision; caches invalidated on change |
| `session_max_minutes` | integer | 60 | 5..240; revocation checked on each command | installation; bounded server session |
| `locale` | enum | browser preference | en or es, then en fallback | member; persisted |
| `person_entity_id` | optional entity reference | none | person domain only; duplicate mapping rejected | member; persisted |

Administrator-owned member exceptions are part of the household authorization policy, not a self-service preference. They may change supported profile grants within hard constraints; ordinary member locale/notification settings never expand authority.

Owner-confirmed defaults are recorded as accepted choices; other defaults and bounds remain proposals pending review. Invalid values and contradictory combinations are rejected before saving; unknown future values require an explicit compatibility error. Precedence is fixed invariants, installation constraints, household policy, then member preferences; lower scopes cannot expand permissions. In-flight commands snapshot relevant policy versions, while revocation is checked at the transaction boundary.

Recommended example: all_ha_administrators supplies inherited administration and an ordinary participant receives the restricted profile. Meaningful alternative: setup_administrator limits inherited initial administration to the installer, while an authorized member exception adjusts one supported action without changing identity or domain invariants. Transport secrets are installation concerns and are never domain form fields.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

AuthenticatePrincipal and AuthorizeHouseholdAction are separate use cases. Authentication adapters verify HA identity; MemberRepository maps it to permissions. The application receives a trusted Principal, not an arbitrary member_id as identity. No local passwords or PINs are introduced. A technical HA service principal never inherits an adult role from a caller-supplied field.

| Boundary | Owns | Forbidden dependency |
|---|---|---|
| Domain | Entities, value objects and pure rules | HA, HTTP, SQL, UI frameworks |
| Application | Authorized commands, queries and semantic ports | Concrete adapters and framework DTOs |
| Adapters | Schema mapping, persistence and provider error mapping | Alternate business rules |
| Composition | Explicit deployment wiring | Business decisions |
| Presentation | View models and rendering | Database access or client-only authorization |

```mermaid
flowchart LR
    UI[UI or HA entry] --> UC[Application use case]
    UC --> Domain[Pure domain]
    UC --> Port[Semantic port]
    Adapter[Infrastructure adapter] --> Port
```

Text equivalent: entrypoints call use cases; use cases depend on pure domain and ports; infrastructure implements ports. Architecture checks reject forbidden imports and cycles. Shared contract tests exercise each port adapter; schemas and migration checks enforce durable boundaries.

## 9. UI/UX and content contract

### 9.1 Primary state examples

| State | Visible content |
|---|---|
| Pending | Checking your Home Assistant account. No action required. |
| Action required | Your account is authenticated but is not linked to this household. Ask a household administrator to grant access. |
| Blocked | Your household access is suspended. No changes were saved. Contact an administrator. |
| Partial | The member was updated, but their optional person entity is unavailable. Account access remains linked. |
| Complete | Account linked. Your household role is Restricted member. |

The primary view names current status, retained facts and one next action, followed by descriptive links to the record/operation. Technical codes and correlation IDs are progressively disclosed. Duplicate responses update the same operation status rather than adding notifications. At most one routine notification per transition, with opt-out and bounded retry summaries.

English and Spanish use stable translation keys, base-language matching and English fallback. Mobile, tablet and desktop layouts, keyboard operation, visible focus, non-color status, accessible names, light/dark contrast and reduced motion are acceptance concerns. Untrusted text is rendered inert; no arbitrary HTML, commands or secret-bearing links.

## 10. Failure, recovery, and cleanup

| Failure | Retained facts | Retry / action | Cleanup |
|---|---|---|---|
| Invalid or denied input | Existing business records and form draft | Correct fields or request the proper role | No side effects |
| Stale revision | Current committed aggregate; user's entered fields | Review current state and submit a new deliberate operation | No automatic overwrite |
| Lost response after commit | Domain result and receipt | Look up or replay the same key | Never issue a fresh-key duplicate |
| Downstream projection unavailable | Successful domain result and durable pending event | Bounded backoff, then visible retry | Acknowledge outbox only after safe consumption |
| Restart or cancellation | Committed records; identified pending work | Recover receipts/cursors; compensate only by explicit command | Remove listeners and owned temporary artifacts |

Errors explain impact, safe cause, action and retained state. External availability is distinct from authorization denial. Retries are bounded and use deterministic backoff tests, not real waits.

## 11. Security, permissions, and privacy

Backend authorization applies to reads and writes. All requests and HA values are untrusted input; only authenticated principals and validated adapter context establish identity. Cross-household IDs, replayed operations and stale roles are covered in the inventory. A person entity and selected member ID do not authenticate a caller. Logs, traces, exports and browser artifacts redact credentials and unnecessary personal data. The technical HA principal has explicit narrow grants and cannot impersonate a household administrator.

## 12. Observability and operational UX

Show operation state and projection freshness to members; expose sanitized correlation, source event, aggregate revision, duration and safe error code to operators. No raw credentials or unrestricted HA payloads enter diagnostics. Counters distinguish denied, invalid, conflict, unavailable and completed operations. One durable activity entry per business transition; retries do not multiply notifications. No telemetry leaves the installation by default.

## 13. Compatibility, migration, rollout, and rollback

The existing M1 database is versioned and its identity, household, history and operation records must be preserved. Implementing these prospective task policies requires reviewed compatible migrations; this documentation-only change introduces no new stored domain records. Upgrade fixtures cover pending operations and ledger compatibility; a backup precedes destructive migration. Unknown future schemas block writes. Downgrade requires a compatible image/database pair, never silent interpretation of newer data.

Both Supervisor and standalone are first-release acceptance targets. Stable and Edge use separate credentials, IDs, volumes and endpoint bindings. Experimental artifacts cannot automatically promote production. Publication, merge and deployment remain in the existing authorized maintainer lifecycle.

## 14. Testing strategy and numeric budget

Minimum: 30 distinct cases, derived from the explicit risk inventory below. Each inventory row counts once. The budget is a floor, not a claim of completeness or executed tests.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Domain and configuration | 6 | two members linked to one HA user; an adult creating an ordinary household task; removal of the last active administrator |
| Security and privacy | 9 | only a person entity ID; a viewer calling task completion directly; a restricted member reading another member's private preferences |
| Adapters and identity | 2 | a valid HA user authentication; an archived account |
| State and concurrency | 6 | a suspended member's existing session; concurrent reassignment and a role downgrade; a concurrent verification-policy change |
| Deployment and contracts | 3 | a forged identity header on standalone HTTP; a verified HA session through Ingress |
| UI and accessibility | 2 | Spanish member preferences; notification opt-out |
| Integration and recovery | 2 | differing task durations and equal points |
| Total | 30 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| household-identity-C01 | Domain and configuration | household-identity-R1 | Given two members linked to one HA user, the second association is rejected. |
| household-identity-C02 | Security and privacy | household-identity-R1 | Given only a person entity ID, a request cannot authenticate. |
| household-identity-C03 | Adapters and identity | household-identity-R1 | Given a valid HA user authentication, the corresponding active member is resolved without matching display names. |
| household-identity-C04 | Security and privacy | household-identity-R2 | Given a default viewer without task-completion permission calling completion directly, the backend denies it and preserves the task. |
| household-identity-C05 | Security and privacy | household-identity-R2 | Given a restricted member reading another member's private preferences, the backend denies the request. |
| household-identity-C06 | Domain and configuration | household-identity-R2 | Given an adult creating an ordinary household task, the role matrix permits it and records the actor. |
| household-identity-C07 | State and concurrency | household-identity-R3 | Given a suspended member's existing session, the next command is denied. |
| household-identity-C08 | State and concurrency | household-identity-R3 | Given concurrent reassignment and a role downgrade, authorization is checked at the command transaction boundary. |
| household-identity-C09 | Adapters and identity | household-identity-R3 | Given an archived account, historical task and ledger views retain its stable actor reference. |
| household-identity-C10 | Deployment and contracts | household-identity-R4 | Given a forged identity header on standalone HTTP, authentication fails. |
| household-identity-C11 | Deployment and contracts | household-identity-R4 | Given a verified HA session through Ingress, the correct user is resolved without a shared administrator fallback. |
| household-identity-C12 | Security and privacy | household-identity-R4 | Given expired upstream authorization, token renewal fails closed and diagnostics omit token material. |
| household-identity-C13 | Domain and configuration | household-identity-R5 | Given removal of the last active administrator, validation rejects the command. |
| household-identity-C14 | Security and privacy | household-identity-R5 | Given a restricted member editing task point values, the backend denies the request. |
| household-identity-C15 | State and concurrency | household-identity-R5 | Given a concurrent verification-policy change, completion uses the persisted policy revision and returns a conflict if stale. |
| household-identity-C16 | UI and accessibility | household-identity-R6 | Given Spanish member preferences, navigation and notification text use Spanish with English fallback for missing keys. |
| household-identity-C17 | UI and accessibility | household-identity-R6 | Given notification opt-out, routine participation summaries are suppressed. |
| household-identity-C18 | Integration and recovery | household-identity-R6 | Given differing task durations and equal points, participation reports show effort and counts alongside points. |
| household-identity-C19 | Security and privacy | household-identity-R2, household-identity-R3 | Given an operation committed before the member was suspended, replay or lookup after suspension returns no protected result and cannot invoke the old privilege. |
| household-identity-C20 | Security and privacy | household-identity-R1, household-identity-R2 | Given an unlinked authenticated user arriving before household setup is finished, access does not become administrator merely because that browser connected first. |
| household-identity-C21 | Deployment and contracts | household-identity-R1, household-identity-R7 | Given default all_ha_administrators, an authenticated proven HA administrator receives inherited Domus administration while an ordinary HA user or technical transport credential does not. |
| household-identity-C22 | Domain and configuration | household-identity-R7 | Given setup_administrator, the proven HA administrator explicitly completing setup receives the initial role and a different HA administrator is not automatically elevated by that alternate mapping. |
| household-identity-C23 | Security and privacy | household-identity-R1, household-identity-R7 | Given selected_ha_user, only the verified active selected account receives initial administration; caller-supplied names, forged flags or an unverified target cannot complete setup. |
| household-identity-C24 | State and concurrency | household-identity-R3, household-identity-R7 | Given an authorized mapping change, inherited grants are reevaluated with their source and independent explicit grants stay distinct; an old mapping revision cannot authorize a later command. |
| household-identity-C25 | Integration and recovery | household-identity-R3, household-identity-R7 | Given all_ha_administrators with externally revoked HA administrator status or a removed final account, the invalid inherited grant is not retained and authenticated recovery is required rather than promoting the next browser. |
| household-identity-C26 | State and concurrency | household-identity-R2, household-identity-R3 | Given a household profile allowance and an explicit member denial saved during an active session, the denial takes precedence and a stale cached allowance cannot authorize the next command. |
| household-identity-C27 | Security and privacy | household-identity-R2, household-identity-R5 | Given an unauthorized self-grant or an allowed action aimed at another household, the backend rejects the policy/command and neither profile customization nor member exceptions bypass scope or adult-verification invariants. |
| household-identity-C28 | State and concurrency | household-identity-R5, household-identity-R7 | Given a mapping/profile/suspension change that would remove the final active effective administrator, the Domus transaction rejects it with current policy intact, including concurrent changes. |
| household-identity-C29 | Domain and configuration | household-identity-R2 | Given a household profile denial for a supported ordinary action and an authorized explicit member allowance, the backend permits only that action within scope while unrelated denied actions remain denied. |
| household-identity-C30 | Domain and configuration | household-identity-R2 | Given contradictory allow/deny entries for the same permission at the same precedence level, saving rejects the policy with prior effective permissions retained instead of resolving it to an accidental grant. |

Every implemented first-party module starts with meaningful behavior tests. Target and proposed merge gate: 100% lines/statements/functions/branches where the selected tools expose those metrics, enforced separately across backend, frontend and integration code. Third-party/generated artifacts are distinguished from authored source; broad exclusions cannot hide untested logic. The partial M1 backend now has independent statement/branch coverage; full identity journeys, UI and HA integration remain pending.

Inject deterministic clocks, IDs, provider fakes and transaction failures. Use semantic assertions alongside golden content, real adapter contracts and disposable HA integration environments. Add Google Chrome evidence from the owner's authorized local HA for real UX; it does not replace automated tests or unit coverage. CI Check runs the complete applicable suite for every PR update.

## 15. Documentation and discoverability

The following documentation operations are relative to develop at e8fa5bbc9ffa179aa7559831f5f3d067c9c9c65c. This policy refinement adds no runtime or test implementation evidence.

| Path | Change |
|---|---|
| specs/household-identity.md | update |
| specs/README.md | reference |
| specs/_template.md | reference |
| specs/catalog.json | update |
| specs/CATALOG.md | update |
| docs/architecture.md | reference |
| docs/product-vision.md | reference |
| docs/glossary.md | reference |
| docs/decisions.md | update |
| docs/reference-investigation.md | reference |
| docs/copilot-adoption.md | reference |
| docs/operations.md | reference |
| docs/user-guide.md | update |
| docs/contracts/home-assistant.md | reference |
| docs/acceptance-plan.md | update |
| docs/roadmap.md | reference |
| README.md | update |
| specs/household-tasks.md | update |
| specs/household-inventory.md | update |
| specs/points-rewards.md | update |
| docs/sdd-validation.md | update |
| docs/evidence/task-policy-sdd-review.json | create |

| Audience | Artifact | Required content |
|---|---|---|
| Member | [User guide](../docs/user-guide.md) | Normal path, defaults and state meaning |
| Administrator/operator | [Operations](../docs/operations.md) | Setup, permissions, recovery, backup and rollback |
| Contributor | [Architecture](../docs/architecture.md) | Boundaries and executable constraints |
| HA consumer | [Entity/service contract](../docs/contracts/home-assistant.md) | Stable schemas, semantics and error handling |
| Reviewer | [Acceptance plan](../docs/acceptance-plan.md) | Tests, coverage and human evidence |

Link/path validation accompanies updates. Implementation changes update the owning SDD, catalog evidence, actual tests and user documentation together.

## 16. Acceptance scenarios

The Given/When/Then-equivalent observable scenarios in section 14 are the executable acceptance inventory. For each case, the given precondition and action must produce the specified result with state and side-effect assertions; tests are not implementation snapshots.

Acceptance includes normal, alternative, invalid, duplicate, concurrent, partial, failure, recovery, security, localization and accessibility paths as allocated above. Human review verifies the primary-state examples on desktop/mobile and light/dark themes. Live acceptance remains pending until an implemented artifact is exercised; no result is inferred from the budget.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| household-identity-R1 | household-identity-C01, household-identity-C02, household-identity-C03, household-identity-C20, household-identity-C21, household-identity-C23 |
| household-identity-R2 | household-identity-C04, household-identity-C05, household-identity-C06, household-identity-C19, household-identity-C20, household-identity-C26, household-identity-C27, household-identity-C29, household-identity-C30 |
| household-identity-R3 | household-identity-C07, household-identity-C08, household-identity-C09, household-identity-C19, household-identity-C24, household-identity-C25, household-identity-C26 |
| household-identity-R4 | household-identity-C10, household-identity-C11, household-identity-C12 |
| household-identity-R5 | household-identity-C13, household-identity-C14, household-identity-C15, household-identity-C27, household-identity-C28 |
| household-identity-R6 | household-identity-C16, household-identity-C17, household-identity-C18 |
| household-identity-R7 | household-identity-C21, household-identity-C22, household-identity-C23, household-identity-C24, household-identity-C25, household-identity-C28 |

All requirement cases are reciprocal with section 14. Domain invariants are owned by pure policy, command/state rules by application use cases, provider behavior by adapters, and visible content by presentation; the boundary table in section 8 assigns these responsibilities. Evidence and user/operator documentation are linked in section 15.

## 18. Implementation sequence

1. Resolve the blocking decisions and review this contract before Ready for implementation.
2. Establish test harness, CI Check and architecture checks with the first source files.
3. Implement pure policies and their complete branch tests, then transactional use cases.
4. Add adapters, schema/error contracts, retry/race fixtures and both deployment wiring paths.
5. Build the accessible localized UI and HA projections with tests alongside each flow.
6. Verify migration, recovery, security, channel isolation and documentation.
7. Run the complete suite, review coverage, perform local Chrome dogfooding with recorded cleanup, and collect human evidence.

These are internal implementation steps within the first integrated release; they do not remove other domains or deployment targets from launch.

## 19. Definition of Done

- [ ] Every normative requirement has observable acceptance and reciprocal case links.
- [ ] Every declared case is implemented meaningfully; the numeric budget is met.
- [ ] Clean Architecture constraints and port contracts pass.
- [ ] All supported first-party coverage metrics reach 100% from the first implementation.
- [ ] CI Check passes for the current PR revision with no omitted required jobs.
- [ ] Configuration, state, permission, idempotency and recovery behaviors agree.
- [ ] Primary UI states, localization, responsive behavior and accessibility pass.
- [ ] Both deployment targets and isolated Stable/Edge channels pass acceptance.
- [ ] User/operator documentation, schema/migration evidence and catalog paths are current.
- [ ] Local Google Chrome evidence identifies the artifact, channel, test records and cleanup.
- [ ] The original Copilot validations pass when their real prerequisites exist; no check is weakened.
- [ ] No material decision blocking readiness remains unresolved; Copilot remains unchanged.

## 20. References and decisions

Primary sources: [Copilot standard](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/specs/README.md), [original template](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/specs/_template.md), and the linked [reference investigation](../docs/reference-investigation.md).

Confirmed owner choices and unresolved proposals are separated in [decisions](../docs/decisions.md). [Issue #2](https://github.com/vypdev/domus/issues/2) tracks the documentation foundation. The [adoption note](../docs/copilot-adoption.md) records the current catalog evidence limitation. Optional future depth remains explicitly deferred in the product vision; the gateway's installation and MCP internals are outside Domus scope.

### Partial M1 identity checkpoint — 2026-10-31

The [implementation companion](platform-foundation-identity-sqlite.md) records pure identity/mapping/permission rules, transaction-bound local authority, member/policy persistence and the session-lease core. [Source-identified evidence](../docs/evidence/m1-identity-policy.json) distinguishes executable policy/storage/provider-fixture tests from pending HA protocol, complete member commands, UI, recovery and target acceptance. This specification remains Draft; no planned acceptance inventory is declared complete by the partial checkpoint.
