# Product catalog, pantry stock and replenishment

- Status: Draft
- Date: 2026-10-28
- Catalog capability ID: household-inventory
- Last verified: 2026-10-31 (document structure only; no implementation evidence)
- Owners: Domus maintainer; engineering/product reviewers to be assigned
- Scope: The household knows what is available, where it is stored and what needs replenishment through a local product catalog and an immutable stock movement ledger.
- Related issues/PRs: https://github.com/vypdev/domus/issues/2
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: Unit/package policy; reservation/replenishment review; barcode library/device evidence; external lookup provider feasibility, terms and response contract. The owner confirmed barcode scope, adjustable material recording and pending regularization rather than negative stock for task material shortfalls on 2026-10-29. Catalog gate prerequisites remain unverified.

## 1. Executive summary

The household knows what is available, where it is stored and what needs replenishment through a local product catalog and an immutable stock movement ledger.

```text
Authenticated member -> validated domain command -> durable result -> household and HA projections
```

This is a prospective Draft, not an implemented or accepted capability. The first usable release covers all domains and both deployment targets.

## 2. Problem, current behavior, and evidence

A large pantry contains long-life supplies in different packages and storage places. Editing a quantity directly loses receipt, consumption and adjustment history.

At the original documentation baseline on 2026-10-28, these domain workflows had no implementation. The merged M1 identity/storage foundation now has separate backend evidence. The task approval and material-authority additions in this review remain prospective; this documentation change adds no runtime behavior.

Evidence: the owner's attached brief and subsequent decisions in [product vision](../docs/product-vision.md), the pinned [reference investigation](../docs/reference-investigation.md), and the existing repository baseline. Retrospective classification is not applicable: no as-built product baseline is reconstructed.

## 3. Actors, surfaces, and terminology

Actors: Household member; receiver; authorized stock administrator; replenishment policy.

Primary surfaces: application UI, HTTP domain boundary, relevant HA entities/services, activity and diagnostics. Definitions of member, principal, occurrence, demand and ledger are shared in the [glossary](../docs/glossary.md). The actor recording an action is distinct from its selected target and actual performer.

## 4. Goals, non-goals, and fixed invariants

Goals and fixed invariants are the following normative requirements. No configuration may weaken authorization, ledger integrity, attribution or idempotency.

| Requirement | Behavior |
|---|---|
| household-inventory-R1 | Product identity, package presentation and base measurement unit MUST be distinct and conversions exact. |
| household-inventory-R2 | Every stock change MUST be an immutable, attributable movement; corrections append compensating records rather than deleting history. |
| household-inventory-R3 | Stock and reservations MUST prevent accidental negative availability and handle concurrent consumption and balanced transfers; insufficient stock in an already-performed task MUST retain a pending consumption intent without inventing a stock movement or blocking completion. |
| household-inventory-R4 | Replenishment MUST use minimum/target policies and stable source identities without duplicating task material demand or manual shopping extras. |
| household-inventory-R5 | Receipt integration MUST post only received quantities once and preserve partial-receipt and retry history. |
| household-inventory-R6 | Locations, optional lots and expiry information MUST remain queryable without inferring that expired stock disappeared. |
| household-inventory-R7 | Barcode entry MUST support camera scanning, manual fallback, local validation/catalog search and optional configured Internet product lookup, with explicit camera permission, safe candidate validation and usable local operation when lookup is absent or fails. |
| household-inventory-R8 | Inventory permissions, inactive products, backup/restore and pagination MUST preserve ledger integrity and household privacy. Validated task-linked consumption MUST accept the configured narrow task authority by default without general inventory permission, while unrelated movements still require their own grants. |

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

Product owns identity, brand, category, barcode references, description, optional image, active flag and base unit. PackagePresentation owns pack count and conversion to that base unit; six 1-litre cartons may be six pieces or six litres according to a fixed product unit, never both without explicit conversion. Location, optional Lot(expiry, received_at), StockMovement, Reservation and ReplenishmentPolicy are separate records. Quantity uses exact decimal arithmetic. Transfer has balanced source/destination legs in one transaction. Availability equals physical stock minus active reservations. Consumption is explicit; estimates and predictions are future suggestions, not silent stock decrements.

Task completion may submit explicitly reviewed actual material quantities in the same user action, as confirmed by the owner. Inventory processes those linked intents through the same stock/movement rules as a standalone movement, with validated task-scoped or applicable inventory authority; planned requirements are not proof of usage. Each intent has a stable completion-cycle/line identity and operation outcome. Consuming a task's own reserved material converts that reservation to consumed while decrementing physical stock in the same transaction, so availability is not charged twice. Other tasks' reservations cannot be stolen silently. A task reopen or verification rejection never adds a physical return: a real return/correction is a distinct authorized movement with an explicit reason.

If a submitted material line lacks sufficient usable stock, save a pending_regularization consumption intent while the performed task completes, as confirmed by the owner. The intent is not a StockMovement and does not lower physical or available stock below zero. Keep its requested quantity, location, completion-cycle/line identity, actor and shortage reason visible. The affected quantity is labeled as recorded stock with a discrepancy requiring review, not silently presented as a verified physical count. No partial decrement within that line is silently substituted for the confirmed quantity. Authorized regularization reviews missing receipts, actual counts or erroneous usage, then posts a validated movement or records an explained correction/dismissal of the intent. A restock event alone does not settle it. Settlement, movement and operation receipt commit together; retries cannot post the line twice. A pending intent is not another reservation or purchasing demand, so it cannot double-count an existing material/replenishment source. Explicit zero usage is not_used and creates no stock movement.

The owner confirmed camera scan and manual entry with optional Internet product lookup on 2026-10-29, closing the missing barcode-scope decision from the truncated attachment. Local catalog lookup runs first. An administrator may configure an external provider; unknown-code lookup is on demand by default. Only the barcode and required provider authentication leave the server boundary, never camera frames, household identity or stock history. Provider responses are untrusted candidates with source/provenance; users review a candidate before importing or matching a product/presentation. No provider is selected or advertised as available yet; feasibility, terms, rate limits and household-product coverage remain adapter review gates.

The owner confirmed on 2026-10-31 that a restricted member authorized to complete a task may explicitly record consumption of that task's linked materials by default, without general inventory permission. The household supplies this task-scoped default and an administrator-authorized per-task override may change it. Explicit applicable member denials, installation limits and current task authorization still take precedence; absence of a general stock grant is distinct from an explicit denial of the scoped material action. Resolve eligible material identities, products, units and locations from the server-owned task/completion snapshot; a client-provided task ID or material line is not a general stock grant. Keep the previously accepted adjustable actual quantities, including zero usage. This authority cannot add unrelated products, change storage targets, edit stock arbitrarily, configure its own permission or reach another household. Inventory remains responsible for validating and posting every movement, usable stock and reservations.

If task-scoped consumption is disabled and the actor lacks the applicable inventory authority, retain otherwise valid performed work and the validated linked usage as visibly unposted pending authorization. Do not claim that stock was consumed, discard the reported work or silently request broader access. This normal policy outcome is distinct from forged identity, unrelated/foreign material references or invalid quantities, which still fail admission before new side effects. A later grant or adult approval does not automatically execute a retained material intent: an authorized explicit settlement reuses its completion-cycle/line identity and rechecks current authority and stock. Stock shortage remains pending_regularization, with no negative stock; it is not the same reason as missing authority. Engineering state labels and schema bounds remain subject to implementation review.

Verification controls point eligibility independently of physical usage. An eligible material movement may post while work awaits adult approval; rejection or reopening never fabricates a physical return. Replaying the original completion, approving it or changing either policy cannot consume again. Retained receipts/history explain the original effective policy but never authorize a newly revoked movement.

The distinct new cross-domain scenarios are owned by the [Tasks acceptance inventory](household-tasks.md); this document does not count copies of them as new cases.

### 6.2 States and alternatives

Product active -> inactive without deleting history. Reservation active -> consumed/released. Consumption intent -> pending_authorization, posted or pending_regularization -> posted/corrected/dismissed with retained reason. A pending_authorization intent stays unposted until explicit authorized settlement rechecks authority and stock; that settlement may post it or retain a stock shortfall as pending_regularization. These are proposed engineering state labels for the owner-confirmed retained-work outcome. Receipt -> posted movement; correction -> compensating movement. Low-stock demand open -> updated -> satisfied, retaining a stable policy/source identity. Optional lot expiration warns but does not silently remove stock.

A duplicate uses its original operation receipt. A changed payload under the same key is a conflict. Out-of-order events use aggregate revision and source identity. Cancellation never erases an already committed ledger effect; compensation is explicit.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| `base_unit` | unit code | piece | piece, gram, millilitre or explicitly supported compatible unit; immutable after movements without migration | product; persisted |
| `minimum_stock` | decimal | 0 | nonnegative, <= target_stock | product/location policy; versioned |
| `target_stock` | decimal | 0 | nonnegative, >= minimum_stock | product/location policy; versioned |
| `expiration_tracking` | boolean | false | requires optional lot dates when enabled; no fabricated date | product; persisted |
| `negative_stock_policy` | enum | reject | reject initially; corrections require a reason | household invariant |
| `external_product_lookup` | enum | off until a provider is configured, then on_demand | off, on_demand or explicit automatic_unknown; administrator-controlled provider setup | household preference; lookup operation snapshots provider/policy version |

Owner-confirmed defaults are recorded as accepted choices; other defaults and bounds remain proposals pending review. Invalid values and contradictory combinations are rejected before saving; unknown future values require an explicit compatibility error. Precedence is fixed invariants, installation constraints, household policy, then member preferences; lower scopes cannot expand permissions. In-flight commands snapshot relevant policy versions, while revocation is checked at the transaction boundary.

Recommended example: piece-based stock with local product search, no expiry tracking and no external lookup. Meaningful alternative: a product enables lot dates and an administrator configures on-demand lookup, without changing its established base unit or ledger history. Transport secrets are installation concerns and are never domain form fields.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

RecordMovement, TransferStock, ReserveMaterials, CorrectStock and EvaluateReplenishment use StockLedger, ProductRepository and DemandPort. Pure quantity and allocation policies validate units. Ledger movements and reservations share transactional consistency; replenishment uses deterministic source IDs and outbox delivery. Barcode scanning is a client adapter with manual entry fallback. Optional Internet lookup implements ProductLookupPort with bounded requests, candidate schemas, provenance, caching and safe error mapping; neither domain code nor UI primitives import provider SDKs. Remote failure never blocks manual/local catalog workflows.

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
| Pending | Recording stock. No action required. |
| Action required | This pack has no unit conversion. Choose its package format before receiving it. |
| Blocked | Only one unit is available. Nothing was consumed. Review stock or release a reservation. |
| Partial | Stock is saved. Its shopping replenishment requirement is waiting to refresh. |
| Complete | Six litres added to Pantry. View the receipt and movement. |

The primary view names current status, retained facts and one next action, followed by descriptive links to the record/operation. Technical codes and correlation IDs are progressively disclosed. Duplicate responses update the same operation status rather than adding notifications. At most one routine notification per transition, with opt-out and bounded retry summaries.

English and Spanish use stable translation keys, base-language matching and English fallback. Mobile, tablet and desktop layouts, keyboard operation, visible focus, non-color status, accessible names, light/dark contrast and reduced motion are acceptance concerns. Untrusted text is rendered inert; no arbitrary HTML, commands or secret-bearing links.

## 10. Failure, recovery, and cleanup

| Failure | Retained facts | Retry / action | Cleanup |
|---|---|---|---|
| Invalid or denied input | Existing business records and form draft | Correct fields or request the proper role | No side effects |
| Valid work with missing material authority | Performed work and validated linked usage remain; no stock movement | Explicit settlement by a currently authorized actor | Never treat a later grant or task approval as automatic consumption |
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

Minimum: 35 distinct cases, derived from the explicit risk inventory below. Each inventory row counts once. The budget is a floor, not a claim of completeness or executed tests.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Domain and configuration | 9 | a six-pack of one-litre cartons in a litre-based product; incompatible kilogram and piece units without conversion; a product with movements |
| Adapters and persistence | 4 | an adjustment with a reason; expiration tracking disabled |
| Security and privacy | 5 | deletion of an existing movement; scanning without external lookup configured; a viewer trying stock correction |
| State and concurrency | 6 | a corrected receipt; simultaneous consumption of the last unit; a stock transfer failure between its two legs |
| Integration and recovery | 8 | task-reserved stock; a manual extra demand; four of six purchased units received |
| UI and accessibility | 2 | an approaching expiry; denied camera permission |
| Deployment and contracts | 1 | an inactive product or paginated stock query |
| Total | 35 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| household-inventory-C01 | Domain and configuration | household-inventory-R1 | Given a six-pack of one-litre cartons in a litre-based product, receipt adds exactly six litres. |
| household-inventory-C02 | Domain and configuration | household-inventory-R1 | Given incompatible kilogram and piece units without conversion, validation rejects the movement. |
| household-inventory-C03 | Domain and configuration | household-inventory-R1 | Given a product with movements, changing its base unit requires an explicit migration instead of reinterpreting stock. |
| household-inventory-C04 | Adapters and persistence | household-inventory-R2 | Given an adjustment with a reason, the ledger exposes actor, source, timestamp and signed amount. |
| household-inventory-C05 | Security and privacy | household-inventory-R2 | Given deletion of an existing movement, the backend denies it and offers a correction path. |
| household-inventory-C06 | State and concurrency | household-inventory-R2 | Given a corrected receipt, both the original movement and linked compensation remain. |
| household-inventory-C07 | State and concurrency | household-inventory-R3 | Given simultaneous consumption of the last unit, only one transaction succeeds. |
| household-inventory-C08 | State and concurrency | household-inventory-R3 | Given a stock transfer failure between its two legs, neither location balance changes. |
| household-inventory-C09 | Domain and configuration | household-inventory-R3 | Given a reservation larger than available stock, the material shortfall is explicit rather than negative availability. |
| household-inventory-C10 | Domain and configuration | household-inventory-R4 | Given a repeated low-stock evaluation, the same source demand is updated rather than duplicated. |
| household-inventory-C11 | Integration and recovery | household-inventory-R4 | Given task-reserved stock, replenishment calculates availability once and does not add the same reservation twice. |
| household-inventory-C12 | Integration and recovery | household-inventory-R4 | Given a manual extra demand, replenishment changes do not delete or reduce that user intent. |
| household-inventory-C13 | State and concurrency | household-inventory-R5 | Given duplicate receipt messages, one inventory movement exists for each receipt line. |
| household-inventory-C14 | Integration and recovery | household-inventory-R5 | Given four of six purchased units received, stock increases by four only. |
| household-inventory-C15 | Integration and recovery | household-inventory-R5 | Given receipt saved before posting failure, retry posts once and marks that receipt line complete. |
| household-inventory-C16 | Domain and configuration | household-inventory-R6 | Given a product in two locations and two lots, quantities reconcile to the product total. |
| household-inventory-C17 | UI and accessibility | household-inventory-R6 | Given an approaching expiry, the UI shows the lot and date without deleting its quantity. |
| household-inventory-C18 | Adapters and persistence | household-inventory-R6 | Given expiration tracking disabled, a receipt requires no invented expiry date. |
| household-inventory-C19 | UI and accessibility | household-inventory-R7 | Given denied camera permission, the scan view offers manual barcode and product entry. |
| household-inventory-C20 | Domain and configuration | household-inventory-R7 | Given a malformed supported GTIN, local check-digit validation identifies the error. |
| household-inventory-C21 | Security and privacy | household-inventory-R7 | Given scanning without external lookup configured, no image or barcode leaves the installation. |
| household-inventory-C22 | Security and privacy | household-inventory-R8 | Given a default viewer without a stock-correction grant, authorization rejects the correction. |
| household-inventory-C23 | Integration and recovery | household-inventory-R8 | Given a restored backup, physical stock and reservations reconcile to the original ledger. |
| household-inventory-C24 | Deployment and contracts | household-inventory-R8 | Given an inactive product or paginated stock query, history remains available and result bounds are enforced. |
| household-inventory-C25 | Adapters and persistence | household-inventory-R7 | Given an unknown local barcode and an enabled on-demand external lookup, the adapter sends only the barcode and required provider authentication and returns a bounded candidate with source provenance. |
| household-inventory-C26 | Integration and recovery | household-inventory-R7 | Given a provider timeout or rate limit, lookup reports unavailability while manual product creation and local search remain usable without a stock mutation. |
| household-inventory-C27 | Security and privacy | household-inventory-R7 | Given hostile, oversized or incompatible provider fields, validation rejects the candidate and no script, private URL fetch or unreviewed catalog overwrite occurs. |
| household-inventory-C28 | Security and privacy | household-inventory-R7 | Given external lookup off or no provider configured, camera/manual scanning uses local data only and no barcode, frame or household information is sent externally. |
| household-inventory-C29 | State and concurrency | household-inventory-R2, household-inventory-R3 | Given two physical units and a two-unit reservation for the completing task, recording one actual unit leaves one physical unit and one active reserved unit; releasing the unused reservation makes one available, without charging the used unit twice. |
| household-inventory-C30 | Integration and recovery | household-inventory-R2 | Given a task material intent already posted, replaying the completion or the linked inventory command returns that movement once and does not decrement stock again. |
| household-inventory-C31 | Domain and configuration | household-inventory-R2 | Given task reopening or rejected verification after material consumption, physical stock does not increase; a confirmed real return appends its own linked movement. |
| household-inventory-C32 | Integration and recovery | household-inventory-R2, household-inventory-R3 | Given a task consumption line larger than usable stock, save a pending intent and its source while the task completes, with no negative stock, partial hidden decrement or fabricated movement. |
| household-inventory-C33 | State and concurrency | household-inventory-R2, household-inventory-R3 | Given two concurrent authorized settlements of one pending intent, at most one validated movement posts and both responses resolve the same retained intent. |
| household-inventory-C34 | Domain and configuration | household-inventory-R3, household-inventory-R4 | Given restocking while an earlier task consumption is pending, the original intent stays visible for review, stock does not decrease automatically and no duplicate material demand is created. |
| household-inventory-C35 | Adapters and persistence | household-inventory-R2 | Given explicit zero usage on a task material line, the linked result is not_used, no stock movement is fabricated and replay preserves the same factual result. |

Every implemented first-party module starts with meaningful behavior tests. Target and proposed merge gate: 100% lines/statements/functions/branches where the selected tools expose those metrics, enforced separately across backend, frontend and integration code. Third-party/generated artifacts are distinguished from authored source; broad exclusions cannot hide untested logic. No application coverage currently exists.

Inject deterministic clocks, IDs, provider fakes and transaction failures. Use semantic assertions alongside golden content, real adapter contracts and disposable HA integration environments. Add Google Chrome evidence from the owner's authorized local HA for real UX; it does not replace automated tests or unit coverage. CI Check runs the complete applicable suite for every PR update.

## 15. Documentation and discoverability

The following documentation operations are relative to develop at e8fa5bbc9ffa179aa7559831f5f3d067c9c9c65c. This policy refinement adds no runtime or test implementation evidence.

| Path | Change |
|---|---|
| specs/household-inventory.md | update |
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
| specs/household-identity.md | update |
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
| household-inventory-R1 | household-inventory-C01, household-inventory-C02, household-inventory-C03 |
| household-inventory-R2 | household-inventory-C04, household-inventory-C05, household-inventory-C06, household-inventory-C29, household-inventory-C30, household-inventory-C31, household-inventory-C32, household-inventory-C33, household-inventory-C35 |
| household-inventory-R3 | household-inventory-C07, household-inventory-C08, household-inventory-C09, household-inventory-C29, household-inventory-C32, household-inventory-C33, household-inventory-C34 |
| household-inventory-R4 | household-inventory-C10, household-inventory-C11, household-inventory-C12, household-inventory-C34 |
| household-inventory-R5 | household-inventory-C13, household-inventory-C14, household-inventory-C15 |
| household-inventory-R6 | household-inventory-C16, household-inventory-C17, household-inventory-C18 |
| household-inventory-R7 | household-inventory-C19, household-inventory-C20, household-inventory-C21, household-inventory-C25, household-inventory-C26, household-inventory-C27, household-inventory-C28 |
| household-inventory-R8 | household-inventory-C22, household-inventory-C23, household-inventory-C24 |

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

## Inventory effects for reviewed recurring work

- Status: Draft
- Owners: Domus maintainers and the Household Inventory capability
- Scope: Inventory persistence and task integration needed to verify the three remaining cross-domain recurrence obligations
- Source baseline: develop at 9b2495922c57a7fddef7c75885fd22acd6a7bd9a
- Related work: https://github.com/vypdev/domus/issues/57 and https://github.com/vypdev/domus/issues/23

### 1. Executive summary

Give scheduled task material reservations, task-generated replenishment demand and physical movements a production Inventory owner. An accepted fixed recurrence replacement moves only compatible unfulfilled effects linked to the affected work. A task can record real material use. Reopening and independent recurrence invalidation preserve movements from retained work. Original command recovery and restored state preserve each decision once.

### 2. Problem, current behavior, and evidence

The selected baseline has task-owned material intents, scoped posting authority and a transaction-local Inventory port in `backend/src/domus/application/task_material_ports.py`. Production task composition in `backend/src/domus/composition/tasks.py` has no concrete Inventory port. Existing recurrence tests observe work, schedule and review state. The Points consumer from https://github.com/vypdev/domus/pull/58 provides real award and reversal observations. Inventory must provide its own positive reservation, demand and movement controls. This delta adds prospective behavior to `specs/household-inventory.md`.

### 3. Actors, surfaces, and terminology

An authorized household Inventory manager records a material reference and stock and establishes the reservation and demand needed by a task. Existing task material permission rules govern actual posting. A household scheduler uses the existing reviewed replacement command. The original work and its replacement are linked through the accepted operation. A reservation affects availability, demand records a replenishment need, and a movement affects physical stock.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| inventory-recurrence-R1 | A reviewed fixed replacement binds the eligible Inventory effects to the review and transfers each compatible unfulfilled task reservation or demand to its exact linked replacement, with durable provenance and unchanged physical stock. |
| inventory-recurrence-R2 | Authorized task material posting appends an exact original-source movement in the real household ledger. Reopening and recurrence invalidation preserve material effects belonging to retained downstream work. |
| inventory-recurrence-R3 | The authoritative receipts, reservations, demands, movements and retained review state preserve household and source identity across contention, rollback, retry, restart, schema migration and compatible restoration. |

Retain immutable physical history and stable source identities. Keep the wider Inventory catalog, shopping UI, external lookups, Gateway and release work with their owning milestones.

### 5. Current versus proposed product journey

An Inventory manager establishes the material, stock and open effects. The scheduler previews a replacement, confirms the same reviewed state and sees the existing linked batch receipt. Recovery uses the original command key. When an authorized member performs work and records actual material use, the ledger records the physical movement. Reopening source work leaves retained successors and their movements visible to the owning services.

### 6. Functional behavior and state model

Bind reviewed replacement to the exact current source effect identities and state. Move only compatible unfulfilled, slot-linked task effects to the matching replacement under the same transaction. Preserve original identity and provenance and keep manual extras outside the replacement. Incompatible effects remain with their source for review. A stale preview cannot silently apply new effects. Cancellation and planning do not change physical stock.

Resolve material references in the household. Record actual consumption using exact quantities and stable task, cycle, line and source-operation identity. Preserve prior movement history. Insufficient stock uses existing pending regularization behavior. An explicit authorized correction links to its original posting. Recurrence invalidation is independent of correction and preserves completed or started work with its existing movements, reservations and demand. Points reverses only the actual award belonging to the reopened source cycle.

### 7. User-facing configuration

Use the existing household roles, task material policy and reviewed recurrence commands. Keep the existing browser settings, material unit values and completion rules. This slice adds no member configuration or new public task response contract.

### 8. Clean Architecture design

Inventory domain policy owns stock quantities, effect compatibility and linked movement rules. Inventory application services enforce authority and coordinate semantic persistence. Recurrence consumes a transaction-local interface to preview and apply reviewed effects. Task material settlement consumes its existing Inventory port. SQLite implements durable identities and shared transactions. Composition binds both deployment modes to the same implementation. Reuse the existing household permission checks and immutable task material values.

### 9. UI/UX and content contract

Use the existing reviewed plan, recovery, material status and retained work surfaces. Keep their English and Spanish behavior and keyboard access. The real Inventory controls are verified through scoped application calls. Broader Inventory presentation remains outside this increment.

### 10. Failure, recovery, and cleanup

The batch command, affected work, Inventory effects and durable receipt commit together. A write failure leaves the prior state and permits original-key retry. A lost response recovers the committed result. Independent SQLite writers serialize before a competing start or invalidation can create conflicting effects. Review retention and restoration preserve actual stock history and prohibit synthetic compensation.

### 11. Security, permissions, and privacy

Scope every effect, reference and movement to the household. Require existing Inventory permission for administrator commands and the existing task-scoped material authority for posting. Preserve actor and original source identity. Keep unrelated work and manual demand outside a scheduler's affected set.

### 12. Observability and operational UX

Integration tests observe exact old and new linked identities, operation receipt, real ledger movement identity and balance, and the existing retained-work review. Record exact test and check revisions in evidence. Keep historical qualification separate from executions on the new change.

### 13. Compatibility, migration, rollout, and rollback

If migration is needed, start from the actual schema 16 SQLite database and preserve its fixture. Its independently captured SQL has SHA-256 032954fc9be4ca2f96359c34df1e6e2a23e5562a481ddbc8fbcb9dcbbeebeb8b. Keep historical task, Points, household and recurrence records readable. Prove migration and rollback with the real fixture and restore through the supported snapshot flow. Use the same production composition in Ingress and standalone.

### 14. Testing strategy and numeric budget

Minimum 4 distinct cases in this delta. The existing recurrence and Inventory acceptance inventories retain their definitions and counts.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Integration and recovery | 2 | Observable scenarios in the case inventory. |
| State and concurrency | 1 | Observable scenarios in the case inventory. |
| Adapters and persistence | 1 | Observable scenarios in the case inventory. |
| Total | 4 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| inventory-recurrence-C01 | Integration and recovery | inventory-recurrence-R1, inventory-recurrence-R3 | Given a fixed recurrence batch with real open task reservations and demand, a manual extra and observable physical stock, accept the reviewed replacement, lose the response and recover by its original key after restart. Observe each exact linked transfer once, unchanged physical stock and manual demand, and no extra transfer on recovery. |
| inventory-recurrence-C02 | Integration and recovery | inventory-recurrence-R2, inventory-recurrence-R3 | Given real Points awards and actual material consumption on downstream work, reopen the source cycle. Observe one Points reversal linked to the source award, unchanged downstream award, unchanged movement identity and balance, and no stock return. |
| inventory-recurrence-C03 | State and concurrency | inventory-recurrence-R1, inventory-recurrence-R2, inventory-recurrence-R3 | Given independently connected SQLite writers and downstream work that starts before invalidation, preserve work with its actual Inventory effects and at most one retained review. Roll back a deliberately failed reviewed transfer, reject stale review state, and restore a compatible snapshot without duplicate effects or synthetic compensation. |
| inventory-recurrence-C04 | Adapters and persistence | inventory-recurrence-R2, inventory-recurrence-R3 | Given the preserved schema 16 fixture, migrate and verify existing Points and task records. Run an authorized positive material posting through both deployment compositions, observe its exact persisted movement, and verify that insufficient stock and cross-household access do not create movements. |

### 15. Documentation and discoverability

Record the owner delta and implementation evidence with the retained contracts. Keep planned file navigation derived from the following inventory.

[specs/household-inventory.md](household-inventory.md) · [specs/catalog.json](catalog.json) · [docs/evidence/recurrence-calendar-qualification.md](../docs/evidence/recurrence-calendar-qualification.md) · [backend/src/domus/application/fixed\_batch\_review.py](../backend/src/domus/application/fixed_batch_review.py) · [backend/src/domus/application/recurrence\_review.py](../backend/src/domus/application/recurrence_review.py) · [backend/src/domus/composition/tasks.py](../backend/src/domus/composition/tasks.py) · [backend/src/domus/infrastructure/sqlite.py](../backend/src/domus/infrastructure/sqlite.py) · [tests/fixtures/sqlite/v16-inventory-source.sql](../tests/fixtures/sqlite/v16-inventory-source.sql)

| Path | Change |
|---|---|
| specs/household-inventory.md | update |
| specs/catalog.json | update |
| docs/evidence/recurrence-calendar-qualification.md | update |
| backend/src/domus/application/fixed_batch_review.py | update |
| backend/src/domus/application/recurrence_review.py | update |
| backend/src/domus/composition/tasks.py | update |
| backend/src/domus/infrastructure/sqlite.py | update |
| tests/fixtures/sqlite/v16-inventory-source.sql | create |

### 16. Acceptance scenarios

Use the actual persisted effects in the four case rows and exercise the linked retained recurrence scenarios from the parent issue. Distinguish a positive ledger witness from an asserted absence. Check both actual container architectures and browser compositions in CI for the reviewed revision.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| inventory-recurrence-R1 | inventory-recurrence-C01, inventory-recurrence-C03 |
| inventory-recurrence-R2 | inventory-recurrence-C02, inventory-recurrence-C03, inventory-recurrence-C04 |
| inventory-recurrence-R3 | inventory-recurrence-C01, inventory-recurrence-C02, inventory-recurrence-C03, inventory-recurrence-C04 |

### 18. Implementation sequence

Preserve the selected fixture. Implement the minimal transaction-local Inventory domain, commands and SQLite mapping. Wire normal task posting and reviewed batch application. Add compound assertions for exact identity, permission, rollback, concurrency, receipt recovery and restoration. Record checked evidence after execution.

### 19. Definition of Done

All new case rows have actual persisted positive controls and pass on the same reviewed revision. The parent recurrence obligations can cite exact runs. Both compositions, English and Spanish, full global and per-file coverage, amd64 and ARM64, Copilot Verification and Bugbot pass. Catalog publication and runtime acceptance have separate evidence.

### 20. References and decisions

The Inventory owner is `specs/household-inventory.md`. The retained recurrence contracts are `specs/recurrence-calendar.md`, `specs/recurrence-execution-foundation.md` and `specs/recurrence-lifecycle-calendar.md`. Keep existing cases with their owners. The Points consumer in https://github.com/vypdev/domus/pull/58 supplies the authoritative award and reversal witness. This draft records planned behavior.
