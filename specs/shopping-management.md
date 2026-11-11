# Shared shopping demand, purchases and receipt

- Status: Draft
- Date: 2026-10-28
- Catalog capability ID: shopping-management
- Last verified: 2026-10-29 (document structure only; no implementation evidence)
- Owners: Domus maintainer; engineering/product reviewers to be assigned
- Scope: Shopping combines manual intent, replenishment and task materials without losing provenance. Buying an item and physically receiving it are separate recorded facts.
- Related issues/PRs: https://github.com/vypdev/domus/issues/2
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: Detailed demand-coverage and unit fixtures; partial-receipt UX; price/currency precision; launch purchase-session scope. The owner confirmed manual-extra and duplicate-safe automatic consolidation defaults on 2026-10-29. Catalog gate prerequisites remain unverified.

## 1. Executive summary

Shopping combines manual intent, replenishment and task materials without losing provenance. Buying an item and physically receiving it are separate recorded facts.

```text
Authenticated member -> validated domain command -> durable result -> household and HA projections
```

This is a prospective Draft, not an implemented or accepted capability. The first usable release covers all domains and both deployment targets.

## 2. Problem, current behavior, and evidence

Checking a shopping box cannot safely represent outstanding demand, partial purchases, shared shoppers and stock receipt.

Current verified sequence: (1) the repository has a minimal README and installed Copilot automation; (2) no Domus application, public service or tests exist; (3) this contract proposes the behavior to build.

Evidence: the owner's attached brief and subsequent decisions in [product vision](../docs/product-vision.md), the pinned [reference investigation](../docs/reference-investigation.md), and the existing repository baseline. Retrospective classification is not applicable: no as-built product baseline is reconstructed.

## 3. Actors, surfaces, and terminology

Actors: Requester; shopper; receiver; stock administrator.

Primary surfaces: application UI, HTTP domain boundary, relevant HA entities/services, activity and diagnostics. Definitions of member, principal, occurrence, demand and ledger are shared in the [glossary](../docs/glossary.md). The actor recording an action is distinct from its selected target and actual performer.

## 4. Goals, non-goals, and fixed invariants

Goals and fixed invariants are the following normative requirements. No configuration may weaken authorization, ledger integrity, attribution or idempotency.

| Requirement | Behavior |
|---|---|
| shopping-management-R1 | Shopping MUST accept shared multiple lists and free-text products with quantity, unit, notes, priority and optional shopper/store/prices. |
| shopping-management-R2 | Every demand MUST retain its origin, additive or overlapping semantics and any user-requested extra quantity. |
| shopping-management-R3 | Consolidation MUST reject incompatible units and prevent double-counting reservations or silently discarding manual requests. |
| shopping-management-R4 | Purchase, receipt and inventory posting MUST remain distinct states supporting partial quantities and nontracked goods. |
| shopping-management-R5 | Concurrent shoppers and retries MUST not duplicate purchases, receipts or stock movements. |
| shopping-management-R6 | Purchase history and optional sessions MUST retain shopper, dates, quantities and optional store/prices without requiring a receipt image. |
| shopping-management-R7 | Shopping commands and recovery MUST enforce household permissions, show retained partial facts and preserve cancellable outstanding demand. |

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

ShoppingList, Demand(source_type, source_id, product_or_free_text, amount, unit, semantics, revision), PlannedLine, PurchaseSession, PurchaseItem and Receipt. Free-text items need no product record. Demands remain individually attributable when a line is consolidated. Inventory target demand covers target minus available minus outstanding compatible supply; a task reservation is already reflected in availability and is not added twice. Manual demand is additional by default and can explicitly be marked overlapping. Quantities combine only with identical product, compatible units and declared semantics; ambiguous cases remain separate.

The owner confirmed on 2026-10-29 that manual requests are additional by default and automatic stock/material demands consolidate without counting the same requirement twice. Consolidation retains each source and its coverage semantics; matching names alone do not establish overlap. If an automatic four-unit demand already covers a reserved task material, that same material is not added again; a manual extra of two still raises the purchase requirement to six. Distinct independent material needs remain additive. This rule does not silently relabel a manual extra as an automatic threshold.

### 6.2 States and alternatives

Demand open -> planned -> satisfied or cancelled. Purchase planned -> purchased -> partially_received -> received. Stock posting is a separate durable step tied to each receipt line; a received tracked product is pending stock until posting succeeds. Nontracked items finish at receipt without inventory records.

A duplicate uses its original operation receipt. A changed payload under the same key is a conflict. Out-of-order events use aggregate revision and source identity. Cancellation never erases an already committed ledger effect; compensation is explicit.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| `manual_demand_semantics` | enum | additional | additional or explicitly overlapping | demand; persisted |
| `purchase_currency` | ISO currency | selected at setup | one household currency initially; decimal minor-unit validation | purchase session; snapshot |
| `default_list` | list reference | Household shopping | active list only | household; persisted |
| `auto_receive_purchase` | boolean | false | true allowed only with explicit combined-action UI confirmation | household; command snapshot |

These are proposed defaults pending review. Invalid values and contradictory combinations are rejected before saving; unknown future values require an explicit compatibility error. Precedence is fixed invariants, installation constraints, household policy, then member preferences; lower scopes cannot expand permissions. In-flight commands snapshot relevant policy versions, while revocation is checked at the transaction boundary.

Recommended example: keep the defaults above. Meaningful alternative: a member selects Spanish and dark theme while the same household policies remain in force. Transport secrets are installation concerns and are never domain form fields.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

CreateDemand, ConsolidateDemand, RecordPurchase, ReceivePurchase and PostReceiptStock use separate semantic contracts. A receipt ID and line ID are inventory idempotency sources. The application owns source demand arithmetic; the UI never consolidates by name. Inventory changes and purchase status use transaction/outbox coordination with visible pending state.

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
| Pending | Saving the purchase. No action required. |
| Action required | Four cartons were received. Two are still pending. Record the remaining receipt when it arrives. |
| Blocked | This line changed while another shopper was editing it. Your quantities are retained. Review the latest line. |
| Partial | Purchase and receipt are saved. Inventory posting is pending. Retry stock posting. |
| Complete | Six cartons received and added to inventory. View purchase. |

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

No existing Domus application data requires migration yet. The first schema is versioned from its first implementation. Upgrade fixtures cover pending operations and ledger compatibility; a backup precedes destructive migration. Unknown future schemas block writes. Downgrade requires a compatible image/database pair, never silent interpretation of newer data.

Both Supervisor and standalone are first-release acceptance targets. Stable and Edge use separate credentials, IDs, volumes and endpoint bindings. Experimental artifacts cannot automatically promote production. Publication, merge and deployment remain in the existing authorized maintainer lifecycle.

## 14. Testing strategy and numeric budget

Minimum: 21 distinct cases, derived from the explicit risk inventory below. Each inventory row counts once. The budget is a floor, not a claim of completeness or executed tests.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| UI and accessibility | 4 | a free-text fruit item; a consolidated line; a session detail view |
| Domain and configuration | 7 | multiple lists; an invalid negative quantity or malformed currency amount; a manual extra of two units |
| Adapters and persistence | 2 | a low-stock demand and manual extra; a purchase session without prices or image |
| State and concurrency | 3 | six units purchased and four received; two shoppers buying the same remaining quantity; a repeated receipt key |
| Integration and recovery | 4 | a nontracked item received; stock posting failure after receipt; a lost purchase response |
| Security and privacy | 1 | a read-only member attempting receipt |
| **Total** | **21** | No double counting |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| shopping-management-C01 | UI and accessibility | shopping-management-R1 | Given a free-text fruit item, a member adds two kilograms without creating an inventory product. |
| shopping-management-C02 | Domain and configuration | shopping-management-R1 | Given multiple lists, assigning a shopper preserves list ownership and quantities. |
| shopping-management-C03 | Domain and configuration | shopping-management-R1 | Given an invalid negative quantity or malformed currency amount, validation identifies the field. |
| shopping-management-C04 | Adapters and persistence | shopping-management-R2 | Given a low-stock demand and manual extra, both source records remain after consolidation. |
| shopping-management-C05 | Domain and configuration | shopping-management-R2 | Given a manual extra of two units, replenishment does not silently absorb those two units. |
| shopping-management-C06 | UI and accessibility | shopping-management-R2 | Given a consolidated line, expanding it shows each source and its semantics. |
| shopping-management-C07 | Domain and configuration | shopping-management-R3 | Given target 10 and available 6 after a task reservation, replenishment requests four rather than adding the reservation twice. |
| shopping-management-C08 | Domain and configuration | shopping-management-R3 | Given incompatible piece and kilogram demands, the list keeps separate lines. |
| shopping-management-C09 | Domain and configuration | shopping-management-R3 | Given compatible overlapping baseline demands, consolidation uses their declared coverage rather than blindly summing them. |
| shopping-management-C10 | State and concurrency | shopping-management-R4 | Given six units purchased and four received, two remain pending receipt and only four can enter stock. |
| shopping-management-C11 | Integration and recovery | shopping-management-R4 | Given a nontracked item received, it completes without a stock movement. |
| shopping-management-C12 | Integration and recovery | shopping-management-R4 | Given stock posting failure after receipt, receipt stays saved and posting is explicitly pending. |
| shopping-management-C13 | State and concurrency | shopping-management-R5 | Given two shoppers buying the same remaining quantity, a revision conflict prevents duplicate fulfillment. |
| shopping-management-C14 | State and concurrency | shopping-management-R5 | Given a repeated receipt key, inventory contains one movement per receipt line. |
| shopping-management-C15 | Integration and recovery | shopping-management-R5 | Given a lost purchase response, retry returns the original purchase rather than a second session. |
| shopping-management-C16 | Adapters and persistence | shopping-management-R6 | Given a purchase session without prices or image, history still shows shopper, date and items. |
| shopping-management-C17 | Domain and configuration | shopping-management-R6 | Given a partial refund or correction, history records a linked correction rather than rewriting the original purchase. |
| shopping-management-C18 | UI and accessibility | shopping-management-R6 | Given a session detail view, quantities purchased and received are labeled separately. |
| shopping-management-C19 | Security and privacy | shopping-management-R7 | Given a read-only member attempting receipt, the backend denies the mutation. |
| shopping-management-C20 | UI and accessibility | shopping-management-R7 | Given cancellation of an unpurchased line, the UI explains remaining source demand before confirming. |
| shopping-management-C21 | Integration and recovery | shopping-management-R7 | Given partial success followed by retry, the response identifies saved purchase facts and retries only the missing stock post. |

Every implemented first-party module starts with meaningful behavior tests. Target and proposed merge gate: 100% lines/statements/functions/branches where the selected tools expose those metrics, enforced separately across backend, frontend and integration code. Third-party/generated artifacts are distinguished from authored source; broad exclusions cannot hide untested logic. No application coverage currently exists.

Inject deterministic clocks, IDs, provider fakes and transaction failures. Use semantic assertions alongside golden content, real adapter contracts and disposable HA integration environments. Add Google Chrome evidence from the owner's authorized local HA for real UX; it does not replace automated tests or unit coverage. CI Check runs the complete applicable suite for every PR update.

## 15. Documentation and discoverability

The following paths are explicit proposed documentation changes relative to the clean repository baseline; implementation source/test paths are intentionally not invented.

| Path | Change |
|---|---|
| specs/shopping-management.md | create |
| specs/README.md | create |
| specs/_template.md | create |
| specs/catalog.json | create |
| specs/CATALOG.md | create |
| docs/architecture.md | create |
| docs/product-vision.md | create |
| docs/glossary.md | create |
| docs/decisions.md | create |
| docs/reference-investigation.md | create |
| docs/copilot-adoption.md | create |
| docs/operations.md | create |
| docs/user-guide.md | create |
| docs/contracts/home-assistant.md | create |
| docs/acceptance-plan.md | create |
| docs/roadmap.md | create |
| README.md | update |

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
| shopping-management-R1 | shopping-management-C01, shopping-management-C02, shopping-management-C03 |
| shopping-management-R2 | shopping-management-C04, shopping-management-C05, shopping-management-C06 |
| shopping-management-R3 | shopping-management-C07, shopping-management-C08, shopping-management-C09 |
| shopping-management-R4 | shopping-management-C10, shopping-management-C11, shopping-management-C12 |
| shopping-management-R5 | shopping-management-C13, shopping-management-C14, shopping-management-C15 |
| shopping-management-R6 | shopping-management-C16, shopping-management-C17, shopping-management-C18 |
| shopping-management-R7 | shopping-management-C19, shopping-management-C20, shopping-management-C21 |

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

## Protected shopping purchases and partial receipts

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Record one-item household purchases, partial receipts and tracked Pantry postings
- Source baseline: develop at 1c88bb4ee84771644b2135efcbeb5755c9538830
- Open decisions blocking readiness: none for this slice

### 1. Executive summary

Provide one shared Shopping section in the protected Inventory workspace. Record a purchase, confirm quantities as they physically arrive, and post each tracked receipt to Pantry as a separate durable action.

### 2. Problem, current behavior, and evidence

Develop has a protected Pantry catalogue, an append-only stock ledger and per-product replenishment. A stock intake cannot distinguish a purchase, an arrival, and a stock posting. Extend specs/shopping-management.md with a bounded implementation slice.

### 3. Actors, surfaces, and terminology

Current household readers see purchases and physical receipt history. A shopping manager records purchases and physical receipts. An inventory manager posts tracked receipts into Pantry. A pending posting is an already recorded physical receipt with no linked stock movement.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| shopping-receipts-R1 | Record an attributed single-item purchase for a current Pantry product or an untracked free-text item. Show purchased, received, remaining and pending stock amounts and retain attributed receipts. |
| shopping-receipts-R2 | Validate exact positive quantities and revisions in the same transaction as each write. A partial physical receipt cannot exceed the remaining purchased amount. Free-text receipt records do not create Inventory bindings or movements. |
| shopping-receipts-R3 | Post each tracked receipt once through the existing Pantry ledger. A rejected posting keeps the physical receipt pending. Replay returns the original result and a changed payload conflicts. |
| shopping-receipts-R4 | Allow one outstanding tracked purchase per product. Subtract compatible open supply from the existing Pantry recommendation without mutating stock, reservations or task effects. |
| shopping-receipts-R5 | Apply current household and operation permissions to reads, writes and recovery. Preserve legacy data and purchase evidence through upgrade, restart and restore. Qualify both deployments and languages. |

Multi-list demand planning, manual demand consolidation and task demand allocation, purchase sessions, prices, refunds, package conversions, and external buying are separate increments.

### 5. Current versus proposed product journey

A member opens Shopping within Inventory. They choose a Pantry product or enter a free-text item and record the quantity already bought. Later, they record the amount that arrived. They can still see the outstanding amount. An authorized stock manager posts each tracked arrival and can inspect its movement link.

### 6. Functional behavior and state model

A purchase identifies the household, immutable item and quantity, shopper and timestamp. A tracked purchase is open while quantity is due or awaiting stock posting. A free-text purchase uses whole pieces and finishes when fully received. Each physical receipt is attributed and stores its own quantity and posting state. A stock posting has a unique movement link. Stock corrections continue to be separately attributed ledger facts. Derive the remaining Pantry recommendation from the existing exact replenishment projection minus the open purchase's unposted amount, floored at zero. A purchase alone never changes recorded stock. Physical receipt and stock posting each commit independently.

### 7. User-facing configuration

Use the existing product base unit. Pieces and untracked items use whole quantities. Grams and millilitres retain the existing precision and bounds. No monetary configuration is needed for this slice.

### 8. Clean Architecture design

Keep exact quantity and transition rules at the domain or application boundary. Store purchase and receipt records through transaction-scoped ports. Reuse Inventory's ledger writer, command authorization, idempotency journal and protected HTTP compositions. Presentation uses shared HA UI components and displays server-authorized state.

### 9. UI/UX and content contract

Show purchase and arrival amounts distinctly, including amounts awaiting stock posting. Use accessible controls for purchase, partial receipt and posting. Provide English and Spanish labels in Ingress and standalone. A pending operation exposes safe recovery by the original key.

### 10. Failure, recovery, and cleanup

An excessive or stale receipt does not change records or balances. An over-capacity or interrupted stock posting leaves the durable physical receipt pending. Retry posting when space is available. Return original command evidence on retry and distinguish historical results after restoration.

### 11. Security, permissions, and privacy

Derive the household, actor and tracked product binding from current server context. Reads require household.read. Purchases and physical receipts require shopping.manage. Posting requires inventory.manage. Writes retain the existing origin, session and CSRF controls. A client-supplied identifier cannot select a different household or warehouse.

### 12. Observability and operational UX

Use the existing audit and original-operation journal. Show receipt identity, actor, date and linked movement in history with safe status and error messages.

### 13. Compatibility, migration, rollout, and rollback

Verify upgrade from representative schema 22 on develop. Preserve Pantry products, policies, stock, task reservations and existing receipts. Exercise restart and activated snapshot restore with purchases, pending physical receipts and posted movements. Both images follow the established compatibility checks.

### 14. Testing strategy and numeric budget

Minimum nine distinct acceptance cases in this slice.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Shopping workflow | 2 | Observable scenarios in the case inventory. |
| Exact quantities | 1 | Observable scenarios in the case inventory. |
| Concurrency and recovery | 2 | Observable scenarios in the case inventory. |
| Replenishment | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Total | 9 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| shopping-receipts-C01 | Shopping workflow | shopping-receipts-R1, shopping-receipts-R2 | A six-unit tracked purchase and four-unit physical receipt show two due and four pending stock. Posting adds exactly four. |
| shopping-receipts-C02 | Shopping workflow | shopping-receipts-R1, shopping-receipts-R2 | An untracked item can be purchased and received in whole pieces without any product or ledger movement. |
| shopping-receipts-C03 | Exact quantities | shopping-receipts-R2, shopping-receipts-R3 | A fractional piece, over-receipt or capacity failure leaves authoritative amounts intact. A pending receipt remains retryable. |
| shopping-receipts-C04 | Concurrency and recovery | shopping-receipts-R2, shopping-receipts-R3, shopping-receipts-R4 | Competing tracked purchases, receipt revisions and posting writers produce one accepted effect. Replayed commands return their original results. |
| shopping-receipts-C05 | Replenishment | shopping-receipts-R4 | Open tracked supply reduces the Pantry recommendation once. Posting changes ledger stock and open supply without consuming task reservations or settling pending task usage. |
| shopping-receipts-C06 | Authorization | shopping-receipts-R5 | A reader can see scoped history and cannot mutate it. Shopping and Inventory grants fence each write and its recovery. Invalid CSRF and foreign resources are rejected. |
| shopping-receipts-C07 | Compatibility | shopping-receipts-R5 | A representative schema 22 database upgrades with its policy, reservations, stock history and operation receipts intact. |
| shopping-receipts-C08 | Concurrency and recovery | shopping-receipts-R3, shopping-receipts-R5 | Restart and activated restore preserve pending and posted receipts, original and historical operation results, and exact stock. |
| shopping-receipts-C09 | Workspace | shopping-receipts-R1, shopping-receipts-R5 | The accessible Shopping journey records and posts a partial tracked receipt in both deployments, covers both locales and runs on amd64 and ARM64 images. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/shopping-receipts-qualification.md](../docs/evidence/shopping-receipts-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/infrastructure/sqlite.py](../backend/src/domus/infrastructure/sqlite.py) · [frontend/src/presentation/domus-inventory.ts](../frontend/src/presentation/domus-inventory.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/shopping-receipts-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/infrastructure/sqlite.py | update |
| frontend/src/presentation/domus-inventory.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Verify each executable case against the source revision proposed for merge. Keep the full authored backend and frontend coverage gates and both actual-image browser runs.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| shopping-receipts-R1 | shopping-receipts-C01, shopping-receipts-C02, shopping-receipts-C09 |
| shopping-receipts-R2 | shopping-receipts-C01, shopping-receipts-C02, shopping-receipts-C03, shopping-receipts-C04 |
| shopping-receipts-R3 | shopping-receipts-C03, shopping-receipts-C04, shopping-receipts-C08 |
| shopping-receipts-R4 | shopping-receipts-C04, shopping-receipts-C05 |
| shopping-receipts-R5 | shopping-receipts-C06, shopping-receipts-C07, shopping-receipts-C08, shopping-receipts-C09 |

### 18. Implementation sequence

Persist purchases and physical receipt facts, integrate the stock posting writer and Pantry recommendation, expose the protected shopping journey, and qualify migration, recovery and both deployments.

### 19. Definition of Done

Require CI and Bugbot green for the same PR commit. Copilot Verification must pass or have a verified exclusively upstream defect documented with the upstream report. Keep releases and deployment separately authorized.

### 20. References and decisions

This slice qualifies the purchase and receipt parts of shopping-management-C10, shopping-management-C11, shopping-management-C12, shopping-management-C13, shopping-management-C14, shopping-management-C15, shopping-management-C18, shopping-management-C19 and shopping-management-C21.

## Shared shopping list from Pantry, Tasks and manual extras

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: One household shopping list with exact source attribution and independent manual extras
- Source baseline: develop at d8840e4acd61425622f2dc7f571ef0adc9092687
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

Add a shared list in the protected Shopping area. For each Pantry product, show the exact quantity to buy from Pantry replenishment, uncovered task materials and manual extras. Preserve each source and keep untracked manual items distinct.

### 2. Problem, current behavior, and evidence

Develop records Pantry policies, outstanding tracked purchases, partial receipts and task material plans. It offers no shared view of the quantities the household still needs. Extend specs/shopping-management.md for one shared list.

### 3. Actors, surfaces, and terminology

A household reader can browse the list. A member with shopping.request can add an extra. A shopping manager can clear an extra. Task source details are visible only when the member can read Tasks. Incoming supply is the unposted amount of a tracked purchase, including units still due and physical receipts awaiting Pantry posting.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| shared-shopping-R1 | Show one protected household list with exact per-product quantities and paginated provenance from Pantry, open task material plans and manual extras. Use product and base-unit identity for tracked grouping. |
| shared-shopping-R2 | Use current Pantry availability, match a reservation only to its task and material line, and apply compatible incoming supply once to the automatic need. Distinct uncovered task material sources add to that need. |
| shared-shopping-R3 | Persist manual extras as independent requests. Support an exact tracked product amount or an untracked named item in whole pieces. Preserve attribution and allow explicit clearing with a durable original operation. |
| shared-shopping-R4 | Protect reads, writes and recovery with current permissions. Verify concurrency, restart, snapshot restoration, and migration from schema 23. Qualify both deployment targets, both locales and both image architectures. |

Multiple lists, optional overlap for manual requests, purchase allocation to individual sources, pricing, sessions, and package conversions are separate increments.

### 5. Current versus proposed product journey

Open the shared Shopping list from Inventory. See the quantities contributed by Pantry, Tasks and extras, then expand the source details for a product. Add an extra using an existing product or a free-text name. A manager explicitly clears a finished or unwanted extra.

### 6. Functional behavior and state model

Use one read snapshot for stock, reservations, open task occurrences, manual requests and purchases. Read task material plans only for open non-draft occurrences and compatible server-owned bindings. For a line with a recorded task demand, use that remaining quantity instead of its planned quantity. Apply its matching reservation first and allocate unreserved physical availability across the remaining task quantities in stable source order. Preserve pending consumption as a separate task fact.

Take the existing Pantry minimum and target need before incoming supply. Add the uncovered task material amounts. Allocate compatible incoming supply once, first to Pantry, then to task shortages in stable source order. Manual extras add after automatic coverage and persist until explicitly cleared. Do not group by text or use incompatible units. The shared list groups tracked products by their stable ID and retains independent free-text extras. A task that is already covered by a matching reservation cannot add that amount again to the purchase total.

### 7. User-facing configuration

The list uses existing Pantry base units. An extra has a positive exact amount, and untracked extras use whole pieces. No list setup is required.

### 8. Clean Architecture design

Keep quantity allocation in pure domain logic. Read task plans, reservations and shopping records through existing transaction-scoped ports and bounded queries. Persist manual extras through the shopping repository and use the existing protected command and original receipt flow. Presentation renders source facts supplied by the server using the shared HA UI.

### 9. UI/UX and content contract

Show the consolidated quantity, the three origin totals and named task and manual source details. Use accessible bilingual controls and pagination for list and source reads. Show manual add and clear controls only for current permitted actors. The pending command journal recovers a lost response without issuing another write.

### 10. Failure, recovery, and cleanup

Reject malformed and foreign items without changing the list. Concurrent clear requests leave one accepted transition and repeated keys recover the original result. Changes to stock, reservations and purchases recompute the automatic sources without deleting manual requests. Restoration distinguishes historical receipts from current effects.

### 11. Security, permissions, and privacy

Require household.read for the list, tasks.read for task projections, shopping.request for adding and shopping.manage for clearing extras. Apply current authority to original command recovery. Derive actor, household and product binding from the server context. Retain session, origin and CSRF checks.

### 12. Observability and operational UX

Expose request provenance and per-source coverage in the protected workspace. Use the original operation journal for successful writes and existing safe error mapping for rejected writes.

### 13. Compatibility, migration, rollout, and rollback

Migrate a representative schema 23 database to the next version and preserve task reservations, Pantry policies, purchase records, pending and posted receipts and existing operations. Verify migration rollback and activated snapshot restoration with durable extras.

### 14. Testing strategy and numeric budget

Minimum nine distinct cases in this increment.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Consolidation | 3 | Observable scenarios in the case inventory. |
| Task provenance | 1 | Observable scenarios in the case inventory. |
| Manual lifecycle | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Recovery | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Total | 9 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| shared-shopping-C01 | Consolidation | shared-shopping-R1, shared-shopping-R2 | Pantry needs four after a task reservation already covers its material. An additional manual request of two yields six to buy with separate sources. |
| shared-shopping-C02 | Consolidation | shared-shopping-R2 | Independent task shortages add after available stock has been allocated once. Compatible incoming supply covers Pantry and task shortage once. |
| shared-shopping-C03 | Consolidation | shared-shopping-R1, shared-shopping-R2, shared-shopping-R3 | An untracked request and a tracked product with the same label remain separate. Fractional pieces and foreign products are rejected. |
| shared-shopping-C04 | Task provenance | shared-shopping-R1, shared-shopping-R2 | Active task plans and recorded demand use stable material identities. Closed work and pending consumption produce no new task demand. |
| shared-shopping-C05 | Manual lifecycle | shared-shopping-R3, shared-shopping-R4 | Add and clear an attributed extra. Compare competing clears, same-key replay, changed-payload conflict and absence of automatic clearing when the policy or purchase changes. |
| shared-shopping-C06 | Authorization | shared-shopping-R4 | A restricted requester adds an extra and a manager clears it. A viewer cannot write. Revoked grants, invalid CSRF and cursors scoped to other actors or products are rejected. |
| shared-shopping-C07 | Compatibility | shared-shopping-R4 | Representative schema 23 upgrades with prior ledger, task, purchase and receipt data intact. An interrupted migration rolls back. |
| shared-shopping-C08 | Recovery | shared-shopping-R3, shared-shopping-R4 | Restart and activated restore preserve manual sources and distinguish current and historical original commands. |
| shared-shopping-C09 | Workspace | shared-shopping-R1, shared-shopping-R4 | English and Spanish journeys inspect the sources, add and clear an extra and recover the original write in Ingress and standalone on both actual image architectures. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/shared-shopping-list-qualification.md](../docs/evidence/shared-shopping-list-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/application/inventory\_queries.py](../backend/src/domus/application/inventory_queries.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/shared-shopping-list-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/application/inventory_queries.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Run and link the listed cases, exact-head CI and both real-image browser results.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| shared-shopping-R1 | shared-shopping-C01, shared-shopping-C03, shared-shopping-C04, shared-shopping-C09 |
| shared-shopping-R2 | shared-shopping-C01, shared-shopping-C02, shared-shopping-C03, shared-shopping-C04 |
| shared-shopping-R3 | shared-shopping-C03, shared-shopping-C05, shared-shopping-C08 |
| shared-shopping-R4 | shared-shopping-C05, shared-shopping-C06, shared-shopping-C07, shared-shopping-C08, shared-shopping-C09 |

### 18. Implementation sequence

Persist manual extras, project and paginate exact needs and sources, then integrate Shopping and validate migration and recovery.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI and Bugbot green on the same PR commit. Copilot Verification passes or has an exclusively upstream defect documented with its report. Releases and deployments require separate authorization.

### 20. References and decisions

Qualifies shopping-management-C04, shopping-management-C05, shopping-management-C06, shopping-management-C07, shopping-management-C08, and the reservation and supply coverage portions of shopping-management-C09.

## Multi-item purchase sessions from the shared shopping list

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Record a single shopping trip from shared list rows and receive each item independently
- Source baseline: develop at ed41596eaf4ccfcef3b60222e6ff47338cf21b6e
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

A shopping manager can select several rows from the shared Shopping list, enter what was actually bought, and save one purchase session. The session preserves shopper, time, items and each item's existing receipt progress.

### 2. Problem, current behavior, and evidence

The shared list consolidates Pantry replenishment, uncovered Task materials and manual extras. Existing purchase commands record one item and already support physical receipts and separate Pantry posting. A multi-item trip currently needs several independent writes and has no grouped history.

### 3. Actors, surfaces, and terminology

A household reader can browse protected session history. A shopping manager records a session and physical arrivals. An inventory manager posts tracked physical receipts to Pantry. A purchase session groups purchase items made in one trip.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| purchase-session-R1 | A manager selects two to sixteen shared list rows, reviews positive exact amounts in their respective base units, and records one session. |
| purchase-session-R2 | Save the session and every purchase item with one operation receipt. Enforce one open purchase per tracked product even across concurrent sessions and individual purchases. |
| purchase-session-R3 | Provide protected, paginated session history and bounded detail with shopper, time, quantities bought, received, still due and awaiting Pantry posting. Reuse per-item arrival and posting. |
| purchase-session-R4 | Recover the original committed or historical operation with current permissions. Preserve existing purchases, receipt facts and extras through schema 24 migration, restart and activated restoration. |

Pricing, stores, refunds, receipt images, persistent carts, multiple lists, purchase allocation to individual demand sources, package conversions and external ordering are separate increments.

### 5. Current versus proposed product journey

Select rows from the shared list, edit their proposed amounts, and record the trip. Open the session to see every item and its current quantities. Open an item's existing receipt view to record a partial arrival and post a tracked receipt to Pantry.

### 6. Functional behavior and state model

The selection identifies a tracked product or active untracked extra by stable ID. The server resolves labels and units and accepts exact quantities actually bought, which may differ from the recommendation. An untracked extra is measured in whole pieces. Reject a duplicated selection, missing or cleared untracked extra, unknown product, invalid quantity or already open tracked purchase. No partial session or purchase is visible after rejection. Manual extra requests retain their independent lifecycle.

A session is immutable as a grouping and has its own ID, actor and time. Its purchase items retain their existing IDs, current revision and physical receipt lifecycle. A tracked receipt is posted separately through the ledger. A recorded trip creates incoming tracked supply under the existing rule.

### 7. User-facing configuration

No settings are needed. A session has two to sixteen distinct selected rows. Quantities use the selected product's immutable base unit.

### 8. Clean Architecture design

Use the existing protected inventory command boundary, transaction-scoped Shopping port and operation journal. Add a session grouping that points at existing purchase records. Read histories through household-scoped application queries. Use the existing protected workspace and shared HA UI controls.

### 9. UI/UX and content contract

Expose selection and review controls in the shared list to current shopping managers. Retain entered quantities after rejection. Show accessible English and Spanish session history and grouped detail. Each item links to its current physical receipts and the original-command recovery remains available after reload.

### 10. Failure, recovery, and cleanup

A losing concurrent session or invalid item rolls back every write. Same-key replay returns the original session and item identities. Changed payload conflicts. Restoration distinguishes the original historical receipt from effects in the restored database. A failed receipt posting retains the physical arrival.

### 11. Security, permissions, and privacy

Require household.read for reads, shopping.manage for recording and recovering the session, and existing current grants for receiving and posting. Resolve actor, household and list identities server-side. Keep session, origin and CSRF checks and bind pagination to the actor and current scope.

### 12. Observability and operational UX

The history shows attributed session and item facts. Existing original operation receipts and safe error states support retry and recovery.

### 13. Compatibility, migration, rollout, and rollback

Upgrade a representative schema 24 database with existing individual purchases, pending and posted receipts, Pantry effects and manual extras. Verify interrupted migration rollback and activated snapshot recovery. Earlier individual purchases remain individually accessible.

### 14. Testing strategy and numeric budget

Minimum eight distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Workspace | 1 | Observable scenarios in the case inventory. |
| State and concurrency | 1 | Observable scenarios in the case inventory. |
| State and recovery | 1 | Observable scenarios in the case inventory. |
| Input and security | 1 | Observable scenarios in the case inventory. |
| Receipt lifecycle | 1 | Observable scenarios in the case inventory. |
| Query and permissions | 1 | Observable scenarios in the case inventory. |
| Compatibility and recovery | 1 | Observable scenarios in the case inventory. |
| Image workspace | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| purchase-session-C01 | Workspace | purchase-session-R1, purchase-session-R3 | Select tracked and untracked rows, edit exact quantities, and view one attributed session and its ordered items. |
| purchase-session-C02 | State and concurrency | purchase-session-R2 | Race two sessions or an individual purchase for the same tracked product. The losing batch leaves no purchase, session or operation receipt. |
| purchase-session-C03 | State and recovery | purchase-session-R2, purchase-session-R4 | Replay identical keys, reject changed payloads and recover the original IDs after a lost response. |
| purchase-session-C04 | Input and security | purchase-session-R1, purchase-session-R2, purchase-session-R4 | Reject foreign or cleared items, duplicate selections, invalid exact amounts and missing grants without changing accepted business facts. |
| purchase-session-C05 | Receipt lifecycle | purchase-session-R3 | Receive part of a tracked item and all of an untracked item. Post the tracked receipt once. Show separately the bought, received, due and pending stock amounts. |
| purchase-session-C06 | Query and permissions | purchase-session-R3, purchase-session-R4 | Page history, reject a foreign cursor, deny unauthorized writes and recover only with current grants. |
| purchase-session-C07 | Compatibility and recovery | purchase-session-R4 | Upgrade representative schema 24 data, roll back an interrupted migration, restart and activate an earlier snapshot that preserves current and historical operations. |
| purchase-session-C08 | Image workspace | purchase-session-R1, purchase-session-R3, purchase-session-R4 | Exercise list selection, lost session response, history and per-item partial receiving in English and Spanish in both deployments and both actual image architectures. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/purchase-session-qualification.md](../docs/evidence/purchase-session-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/application/inventory\_queries.py](../backend/src/domus/application/inventory_queries.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/purchase-session-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/application/inventory_queries.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Record and recover a two-item trip and partially receive one item. Compare current Pantry supply, per-item receipts and purchase session history through restart and activated restore. Link CI and both image jobs.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| purchase-session-R1 | purchase-session-C01, purchase-session-C04, purchase-session-C08 |
| purchase-session-R2 | purchase-session-C02, purchase-session-C03, purchase-session-C04 |
| purchase-session-R3 | purchase-session-C01, purchase-session-C05, purchase-session-C06, purchase-session-C08 |
| purchase-session-R4 | purchase-session-C03, purchase-session-C04, purchase-session-C06, purchase-session-C07, purchase-session-C08 |

### 18. Implementation sequence

Persist the session grouping, connect the transactional command and protected history, then implement the list selection and receipt journey.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI and Bugbot on the same commit. Copilot Verification passes or an exclusively upstream defect is documented. Releases and deployments require separate authorization.

### 20. References and decisions

Qualifies shopping-management-C16 and shopping-management-C18. Rechecks shopping-management-C10 through shopping-management-C15, shopping-management-C19 and shopping-management-C21 for the grouped flow.

## Cancel the unreceived balance of a purchased item

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Close the unreceived balance of a single purchase item
- Source baseline: develop at c604e25d295217ef0653e47daa90b39a9b3a353b
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

A shopping manager can close a purchase item's entire unreceived balance when the units will no longer arrive. The cancellation has its own reason, actor, time and original operation receipt. The item remains visible in purchases or its session.

### 2. Problem, current behavior, and evidence

An undelivered amount currently counts as incoming supply indefinitely and can block a replacement purchase. In the standalone recovery test, Playwright sometimes loses the response body while checking the recovered session identity.

### 3. Actors, surfaces, and terminology

A household reader can inspect purchase progress and the cancellation. A member with shopping.manage can close the balance. Inventory managers still post already received tracked items through the existing posting flow.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| purchase-balance-R1 | Close the full positive unreceived balance once, with a reason and the current item revision, from the item detail used by purchases and sessions. |
| purchase-balance-R2 | Commit one attributed cancellation and one operation receipt atomically. A racing arrival or a competing cancellation cannot reuse the balance. Same-key replay returns the original result. |
| purchase-balance-R3 | Preserve the original purchased amount, physical receipts and Pantry posting. Remove the canceled amount from incoming supply and recompute remaining need. Only received units awaiting posting still count as incoming after cancellation. |
| purchase-balance-R4 | Protect commands, reads and recovery with current permissions. Verify legacy data, restart, snapshot restoration and schema 25 migration. Stabilize the compiled standalone purchase-session recovery test. |

Refunds, returns, payments, cancellation of a whole session, editable purchase quantities and additional demand controls are separate increments.

### 5. Current versus proposed product journey

Open a purchase item or open its physical receipt detail from a session. Review the amount still due, enter a reason, and close the remaining balance. History shows the purchased, received, pending posting and canceled amounts. A replacement tracked purchase becomes available once the original item has no remaining supply.

### 6. Functional behavior and state model

If six units were bought and four received, the amount canceled is exactly two. Calculate it from the persisted item inside the transaction after checking the expected revision and current permission. Require a nonblank reason of at most 240 characters. A successful operation increases the item revision and links the cancellation to the purchase. There is one cancellation per item. Future arrivals for the closed item are rejected. Previously recorded physical receipts remain eligible for their normal Pantry posting.

Effective incoming for a tracked item is purchased minus settled minus canceled. An item is open only while that quantity is positive. The original purchased amount, receipts, existing stock movements, extras and reservations retain their identities.

### 7. User-facing configuration

Use existing shopping permissions and purchase units. There is no new household setting.

### 8. Clean Architecture design

Use the purchase aggregate for balance and revision rules. The authorized command uses the existing Shopping port, transactional adapter and operation journal. The item detail uses the existing protected workspace and shared controls. Add a linked cancellation record and keep the invariant for one open purchase per tracked product in SQLite.

### 9. UI/UX and content contract

Show the exact quantity to cancel before confirmation, require the reason and display canceled quantity, actor, time and reason afterward. Reuse the same detail for individual items and session items. Keep current localized receipt and recovery interactions in both deployment modes.

### 10. Failure, recovery, and cleanup

Invalid reason, stale revision, no balance, unavailable item and denied permissions leave no mutation. A retry of the original command returns the existing receipt. Restore distinguishes historical operations from effects present in the activated snapshot. Stabilize the Playwright session recovery assertion by capturing the original response before delivering it to the browser.

### 11. Security, permissions, and privacy

Require household.read for purchase queries and current shopping.manage for cancellation and recovery. Use the existing session, origin and CSRF checks. Resolve household, purchase identity and actor at the command boundary.

### 12. Observability and operational UX

Show attributed cancellation history and reuse the safe operation recovery and conflict messages. Recompute the shared list from current authorized sources.

### 13. Compatibility, migration, rollout, and rollback

Upgrade representative schema 25 data with a purchase session, prior purchases, posted and unposted physical receipts, Pantry effects and manual extras. Existing purchases start with zero canceled. Verify interrupted migration rollback and activated restore with both historical and current receipts.

### 14. Testing strategy and numeric budget

Minimum eight distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| State and UI | 1 | Observable scenarios in the case inventory. |
| Inventory projection | 1 | Observable scenarios in the case inventory. |
| State and concurrency | 1 | Observable scenarios in the case inventory. |
| Recovery | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Browser recovery | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| purchase-balance-C01 | State and UI | purchase-balance-R1, purchase-balance-R3 | Cancel two of six after four were received. Preserve all original quantities and show attributed history in item and session detail. |
| purchase-balance-C02 | Inventory projection | purchase-balance-R3 | The canceled amount ceases to count as incoming. Received pending stock still counts until posted. A later tracked purchase can open once the original is settled. |
| purchase-balance-C03 | State and concurrency | purchase-balance-R2 | Race an arrival against cancellation and race two cancellations. Only the winning mutation commits and balance stays valid. |
| purchase-balance-C04 | Recovery | purchase-balance-R2, purchase-balance-R4 | Replay the original key, reject changed payload and recover original and historical results after restart and activated restore. |
| purchase-balance-C05 | Authorization | purchase-balance-R1, purchase-balance-R4 | Reject invalid reasons, foreign purchases, stale revisions, no remaining balance, denied or revoked grants and missing CSRF. |
| purchase-balance-C06 | Compatibility | purchase-balance-R4 | Migrate the schema 25 fixture, verify rollback on failure and preserve prior sessions, receipts and stock facts. |
| purchase-balance-C07 | Workspace | purchase-balance-R1, purchase-balance-R3, purchase-balance-R4 | Cancel from the session item detail and verify the balance, reason, history and replenishment in English and Spanish and both actual image architectures. |
| purchase-balance-C08 | Browser recovery | purchase-balance-R4 | The session recovery test checks the original session ID from a response captured before browser navigation or refresh. Verify standalone and Ingress. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/purchase-balance-qualification.md](../docs/evidence/purchase-balance-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/purchase-balance-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Cancel an unreceived amount while retaining a pending physical receipt. Confirm exact incoming supply before and after its Pantry posting. Race independent connections and recover the original cancellation.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| purchase-balance-R1 | purchase-balance-C01, purchase-balance-C05, purchase-balance-C07 |
| purchase-balance-R2 | purchase-balance-C03, purchase-balance-C04 |
| purchase-balance-R3 | purchase-balance-C01, purchase-balance-C02, purchase-balance-C07 |
| purchase-balance-R4 | purchase-balance-C04, purchase-balance-C05, purchase-balance-C06, purchase-balance-C07, purchase-balance-C08 |

### 18. Implementation sequence

Add the linked cancellation and guarded command, update the item and supply projections, then add the bilingual control and stable browser checks.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI, both actual image architectures and Bugbot on the same commit. Keep the existing Copilot workflow and verification evidence. Releases and deployments require separate authorization.

### 20. References and decisions

Qualifies the linked quantity-correction portion of shopping-management-C17 and exercises original-operation, receipt and shopping-demand invariants.

## Void a physical receipt awaiting Pantry posting

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Void one tracked purchase receipt before Pantry posting
- Source baseline: develop at f067b5c788ece813ef2d21f531e1ff03d1376586
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

A shopping manager can void a mistaken physical receipt and record the correct arrival using the existing flow. The original receipt and its attributed void remain visible on the purchase item.

### 2. Problem, current behavior, and evidence

A pending physical receipt cannot be corrected today. Posting a mistaken quantity would create incorrect Pantry stock. The balance cancellation applies to the undelivered quantity, so it cannot correct a receipt.

### 3. Actors, surfaces, and terminology

Household readers can inspect item and receipt history. A shopping manager records arrivals and can void eligible receipts. Inventory managers post eligible tracked receipts to Pantry.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| receipt-void-R1 | Void one entire tracked physical receipt that has no Pantry posting and belongs to a purchase with no balance cancellation. Require a nonblank reason and the current item revision. |
| receipt-void-R2 | Append an attributed void and update the received quantity, purchase revision and original operation journal atomically. An already voided receipt cannot be posted or voided again. |
| receipt-void-R3 | Preserve original receipts, the purchased amount, other arrivals and existing Pantry movements. The void moves the recorded quantity from received and awaiting posting back to still due. |
| receipt-void-R4 | Enforce current permissions for commands and recovery. Qualify legacy data, schema 26 migration, restart, activated restoration and both protected workspaces. |

Corrections after Pantry posting, untracked receipts, canceled purchase balances, financial refunds, returns and edits to the original receipt are outside this increment.

### 5. Current versus proposed product journey

Open physical receipts on a purchase item, including a session item. Review the amount on the mistaken receipt, enter a reason and confirm the void. The voided receipt stays in history and the user can record the correct quantity through the existing receipt form.

### 6. Functional behavior and state model

Select an existing receipt of the given purchase. Check current permission, the purchase revision, tracked status, no balance cancellation, no Pantry movement and no prior void within one write transaction. Require a nonblank reason of at most 240 characters. Subtract the whole receipt quantity from the effective received amount and advance the item revision once. Keep the original receipt with its identity, quantity, actor and time. Link one void with reason, actor and time. Calculate the change from the original stored exact amount.

The pending posting quantity decreases and the amount still due increases by that exact amount. The original purchased amount and the total compatible incoming supply retain their values. A later arrival uses the current purchase revision. A later purchase balance cancellation applies to the then-current undelivered quantity.

### 7. User-facing configuration

Use existing shopping and inventory permissions and base units. No household setting is needed.

### 8. Clean Architecture design

Keep purchase rules in the aggregate and authorize through the existing command journal. Use transaction-scoped Shopping ports and a linked receipt void record. Guard Pantry posting with the same persisted receipt state. Use the existing item detail and shared UI controls.

### 9. UI/UX and content contract

Show the exact quantity on the confirmation, require a reason, and show the voided status, author, reason and time in the original receipt history. Use localized labels in Ingress and standalone. Show the void control only to shoppers for eligible receipts, and remove the Pantry posting action from a voided receipt.

### 10. Failure, recovery, and cleanup

Invalid, stale, denied and competing commands leave the receipt and balances intact. Only one of a void and a competing Pantry posting can commit. An identical replay returns the original operation result, and a changed payload conflicts. A restored operation can be historical.

### 11. Security, permissions, and privacy

Require household.read for queries and current shopping.manage for voiding and its original receipt recovery. Pantry posting retains its current inventory.manage requirement. Apply existing authentication, context, origin and CSRF checks.

### 12. Observability and operational UX

Retain the attributed original and void in receipt history. Use the existing feedback and original request recovery controls. Preserve current audit and operation receipt semantics.

### 13. Compatibility, migration, rollout, and rollback

Upgrade a schema 26 database with a session, posted and pending receipts, an existing purchase balance cancellation, and original operations. Preserve prior records and verify interruption rollback, restart and activated restoration with current and historical void receipts.

### 14. Testing strategy and numeric budget

Minimum eight distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| State and UI | 1 | Observable scenarios in the case inventory. |
| Inventory projection | 1 | Observable scenarios in the case inventory. |
| Concurrency | 1 | Observable scenarios in the case inventory. |
| Recovery | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Rejection | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| receipt-void-C01 | State and UI | receipt-void-R1, receipt-void-R3 | Void a precise mistaken receipt, retain its original details and attributed reason, then record the correct arrival. |
| receipt-void-C02 | Inventory projection | receipt-void-R3 | Check effective received, pending posting and still due amounts. Preserve original purchased quantity, other arrivals, stock and incoming supply. |
| receipt-void-C03 | Concurrency | receipt-void-R2 | Race posting against voiding and two independent voids. Verify one accepted effect and no ledger movement when the void wins. |
| receipt-void-C04 | Recovery | receipt-void-R2, receipt-void-R4 | Replay the same key, reject a changed payload, and recover current and historical operations through restart and activated restore. |
| receipt-void-C05 | Authorization | receipt-void-R1, receipt-void-R4 | Reject a bad reason, foreign item or receipt, denied or revoked permission and missing CSRF. |
| receipt-void-C06 | Rejection | receipt-void-R1, receipt-void-R2 | Reject stale revisions, untracked, posted, canceled-balance and previously voided receipts. Verify write failure rollback. |
| receipt-void-C07 | Compatibility | receipt-void-R3, receipt-void-R4 | Migrate representative schema 26 data and preserve sessions, previous cancellations and receipts. Check interrupted migration and snapshot integrity. |
| receipt-void-C08 | Workspace | receipt-void-R1, receipt-void-R3, receipt-void-R4 | Void from the session item detail, verify attribution and receive and post the corrected amount in English and Spanish, Ingress and standalone, on amd64 and ARM64. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/physical-receipt-void-qualification.md](../docs/evidence/physical-receipt-void-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/physical-receipt-void-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Record four units against a six-unit purchase, void that receipt and then record the three units that arrived. Post the corrected receipt once. Recover the original void and verify that the original receipt stays visible and cannot be posted.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| receipt-void-R1 | receipt-void-C01, receipt-void-C05, receipt-void-C06, receipt-void-C08 |
| receipt-void-R2 | receipt-void-C03, receipt-void-C04, receipt-void-C06 |
| receipt-void-R3 | receipt-void-C01, receipt-void-C02, receipt-void-C07, receipt-void-C08 |
| receipt-void-R4 | receipt-void-C04, receipt-void-C05, receipt-void-C07, receipt-void-C08 |

### 18. Implementation sequence

Add the linked void and transactional command, guard Pantry posting, expose attributed history and qualify the bilingual interaction with migration, recovery and concurrency tests.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI, both actual image architectures, Copilot verification and Bugbot on the same commit. Keep the installed Copilot resources. Releases and deployments require separate authorization.

### 20. References and decisions

Qualifies the pending physical receipt correction in shopping-management-C17, following the purchase balance cancellation accepted in issue #80.

## Correct a physical receipt posted to Pantry

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Reverse one tracked, posted physical receipt through an attributed Shopping and Pantry correction
- Source baseline: develop at 4ebedb48eb296622c337a6d0f17208a1f4d9de10
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

An authorized member can reverse one mistaken physical receipt that was posted to Pantry. One linked inventory correction removes its exact stock quantity and returns that quantity to the purchase item's outstanding balance.

### 2. Problem, current behavior, and evidence

Shopping supports voiding a physical receipt before posting. Inventory can reverse a posted intake independently, leaving the Shopping receipt recorded as posted. The linked command synchronizes the two records in one transaction.

### 3. Actors, surfaces, and terminology

Household readers see the receipt and its correction. A member with both shopping.manage and inventory.manage can correct a posted receipt. Shopping retains its existing receipt and outstanding balance permissions. Pantry retains its existing permissions for ordinary intake corrections.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| posted-receipt-R1 | Correct one tracked and posted receipt on an item with no balance cancellation. Require both grants, a nonblank reason and the current item revision. |
| posted-receipt-R2 | Commit one exact negative movement linked to the original intake, one receipt correction, effective purchase amounts, revision and original operation receipt atomically. Protect available stock and active reservations. |
| posted-receipt-R3 | Prevent a second correction and preserve the one-open-purchase invariant. Preserve historical standalone reversals and their receipts. Route new Shopping receipt corrections through the linked command. |
| posted-receipt-R4 | Preserve original facts and attribution in both histories. Verify current authorization, concurrent writes, recovery, representative schema 27 migration, restart, activated restoration and both protected workspaces. |

Partial corrections, financial refunds, physical returns, canceled purchase balances and reconciling previously reversed receipts are outside this increment.

### 5. Current versus proposed product journey

Open the purchase item and its physical receipt history, including from a session. On an eligible posted receipt, review the exact quantity, enter a reason and confirm. The original receipt and posting remain visible with the compensating movement. Record and post the correct amount using the existing flows.

### 6. Functional behavior and state model

Bind receipt identity to the household and purchase. Validate the item revision, both grants, tracked status, original stock movement, lack of an existing correction, absence of a balance cancellation and sufficient unreserved stock in one write transaction. Require a nonblank reason of at most 240 characters. If a fully settled purchase would reopen, check that the same product has no other open purchase.

Append a negative intake correction linked to the original movement. Keep the original receipt and posting identifiers, and link the receipt to the new movement. Subtract the whole receipt quantity from both effective received and settled amounts and advance the purchase revision once. Awaiting posting retains the quantities of other active receipts. Still due and incoming supply gain the exact corrected amount. Existing task reservations and manual extras retain their identities.

If an intake was already reversed through Inventory before this increment, display that historical reversal with its original movement and receipt. Preserve the prior purchase projection. Protect the original operation receipt and reject a second reversal. Future standalone Inventory reversal requests for Shopping receipts point users to Shopping.

### 7. User-facing configuration

Use existing base units, grants and purchase revision tokens. No household setting is needed.

### 8. Clean Architecture design

Reuse the Inventory ledger's linked correction and reservation checks. Use transaction-scoped Shopping and Inventory ports and the existing command journal. Persist a link to the compensating movement and derive its attribution from the ledger. Keep pending receipt voids as distinct history.

### 9. UI/UX and content contract

Reuse the protected receipt detail and shared controls. Show the exact quantity before confirming and show the reason, actor, time and linked movement afterward. Distinguish a historical Inventory-only reversal from a linked Shopping correction. Point to Shopping from the Inventory movement history for Shopping receipts. Localize the flow in Ingress and standalone.

### 10. Failure, recovery, and cleanup

A stale, denied or rejected correction changes neither balances nor original receipts. Competing corrections and a competing replacement purchase cannot produce duplicate or conflicting state. Replaying the same key returns the original operation. A changed payload conflicts. Restore can make a prior operation historical.

### 11. Security, permissions, and privacy

Require household.read for history. Both shopping.manage and inventory.manage must be current for the correction and its original operation recovery, including replay. Apply existing authentication, context, origin and CSRF checks.

### 12. Observability and operational UX

Keep both original and compensating movements in the Pantry ledger. Display the linked correction on the receipt and retain the original request recovery workflow. Distinguish conflicts caused by reservations, another open purchase or an earlier correction.

### 13. Compatibility, migration, rollout, and rollback

Upgrade a representative schema 27 database with a Shopping session, a posted receipt, a pending receipt, a receipt void, a purchase balance cancellation, original operations and an Inventory-only reversal. Keep original rows and verify migration rollback and activated restoration with current and historical linked corrections.

### 14. Testing strategy and numeric budget

Minimum nine distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| State and UI | 1 | Observable scenarios in the case inventory. |
| Inventory projection | 1 | Observable scenarios in the case inventory. |
| Concurrency | 1 | Observable scenarios in the case inventory. |
| Recovery | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Rejection | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Snapshot integrity | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Total | 9 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| posted-receipt-C01 | State and UI | posted-receipt-R1, posted-receipt-R2, posted-receipt-R4 | Correct a fractional posted receipt, show the linked history, and receive and post the right amount. |
| posted-receipt-C02 | Inventory projection | posted-receipt-R2 | Preserve exact amounts, other receipts and reservations. Reject a correction below the reservation floor without a ledger write. |
| posted-receipt-C03 | Concurrency | posted-receipt-R2, posted-receipt-R3 | Race two corrections, an identical request, and a competing purchase against reopening. |
| posted-receipt-C04 | Recovery | posted-receipt-R2, posted-receipt-R4 | Replay the same key, reject a changed payload and recover current and historical operations after restart and activated restore. |
| posted-receipt-C05 | Authorization | posted-receipt-R1, posted-receipt-R4 | Require both current permissions and CSRF. Reject foreign identities, revoked grants and unauthenticated reads. |
| posted-receipt-C06 | Rejection | posted-receipt-R1, posted-receipt-R2, posted-receipt-R3 | Reject pending, untracked, canceled, stale or previously corrected receipts, and prove rollback on an injected write failure. |
| posted-receipt-C07 | Compatibility | posted-receipt-R3, posted-receipt-R4 | Migrate schema 27 data, preserve previous voids and Inventory-only corrections, reject a new unlinked reversal and recover the original legacy receipt. |
| posted-receipt-C08 | Snapshot integrity | posted-receipt-R2, posted-receipt-R4 | Verify the receipt, its posting and its linked reversal agree with the purchase totals and revision. |
| posted-receipt-C09 | Workspace | posted-receipt-R1, posted-receipt-R2, posted-receipt-R4 | Correct a posted session receipt and verify both histories in English and Spanish, Ingress and standalone, on amd64 and ARM64. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/posted-receipt-correction-qualification.md](../docs/evidence/posted-receipt-correction-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/posted-receipt-correction-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Post the wrong amount, correct it once, and verify that both the stock and purchase receipt show the linked correction. Check the exact reopened amount, then record and post the corrected arrival. Verify rejection with active reservations and safe original request recovery.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| posted-receipt-R1 | posted-receipt-C01, posted-receipt-C05, posted-receipt-C06, posted-receipt-C09 |
| posted-receipt-R2 | posted-receipt-C01, posted-receipt-C02, posted-receipt-C03, posted-receipt-C04, posted-receipt-C06, posted-receipt-C08, posted-receipt-C09 |
| posted-receipt-R3 | posted-receipt-C03, posted-receipt-C06, posted-receipt-C07 |
| posted-receipt-R4 | posted-receipt-C01, posted-receipt-C04, posted-receipt-C05, posted-receipt-C07, posted-receipt-C08, posted-receipt-C09 |

### 18. Implementation sequence

Add the linked correction and command guards, update stock and receipt projections, localize history and confirmation, and qualify migration, concurrency and recovery.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI, both actual image architectures, Copilot Verification and Bugbot on the same commit. Preserve installed Copilot resources. Releases and deployments require separate authorization.

### 20. References and decisions

Qualifies the posted receipt correction in shopping-management-C17 after issue #82.

## Return a physical receipt posted to Pantry

- Status: Draft
- Owners: Domus maintainers and Shopping Management
- Scope: Record one full physical return from a closed tracked purchase item
- Source baseline: develop at 3e60abdc2ac044bcb0f48e99e4a43f9a6d95dfac
- Open decisions blocking readiness: none for this increment

### 1. Executive summary

Record the physical return of a tracked receipt on a closed purchase. Shopping shows the original receipt and its attributed return. Pantry shows the linked stock withdrawal.

### 2. Problem, current behavior, and evidence

A supplier return removes goods that arrived and were posted correctly. The receipt correction is for a posting error and returns quantity to the amount still due. The physical return needs its own record while the purchase remains closed.

### 3. Actors, surfaces, and terminology

Household readers see receipts and returns. A member with shopping.manage and inventory.manage can record the physical return. A closed purchase item in this increment has its full purchased quantity received and posted with no outstanding-balance cancellation.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| receipt-return-R1 | Return one whole tracked, posted and valid receipt of a fully received and settled purchase item. Require both current grants, a reason and the current purchase revision. |
| receipt-return-R2 | Commit a linked withdrawal, receipt return, new revision and original operation receipt atomically. Validate available stock and active reservations. |
| receipt-return-R3 | A return and any correction of the same receipt are mutually exclusive. Preserve the closed purchase and original history. Recalculate demand using current stock. |
| receipt-return-R4 | Preserve current authorization, exact retry recovery, legacy data, restart and restoration. Show the reason, author, time and linked withdrawal in both workspaces. |

Partial returns, financial refunds, supplier integrations and undoing a physical return have separate acceptance.

### 5. Current versus proposed product journey

From physical receipt history, choose to record the return, review the original amount, enter a reason and confirm. Shopping shows the receipt and return. Pantry history shows a distinct return with its link to the original intake.

### 6. Functional behavior and state model

Resolve the purchase and receipt in the current household. Require a tracked posting and a completely received and posted purchase item with no balance cancellation. Check the expected revision and require a nonblank reason of at most 240 characters. Derive the exact return amount from the persisted receipt. A previously corrected receipt, a historical Inventory-only reversal or an existing return makes the request ineligible.

Append the exact negative Pantry movement and link it to the receipt. Advance the purchase revision once and preserve all original purchase amounts and its closed state. Other receipts and existing reservations retain their identities. Existing replenishment and shared list projections use the resulting stock. An independent open purchase for the same product does not block a return from the closed purchase.

### 7. User-facing configuration

Use existing base units, roles and purchase revisions. No household setting is needed.

### 8. Clean Architecture design

Reuse the ledger writer, stock floor checks, transaction-scoped ports and original operation journal. Persist an attributed return through its linked stock movement. Keep return and correction eligibility in the same transaction.

### 9. UI/UX and content contract

Show the exact quantity before confirmation. The purchase detail shows the return reason, author, time and movement link. The movement history distinguishes the withdrawal from a stock correction. Localize the action and recovery in both Ingress and standalone.

### 10. Failure, recovery, and cleanup

An invalid, stale or rejected return changes no business state. Only one competing return or correction can commit. A repeated key returns the original operation. A changed payload conflicts. Restoration can make an earlier operation historical.

### 11. Security, permissions, and privacy

Require household.read for history and both current grants for mutation and recovery. Apply the existing verified context, origin and CSRF checks.

### 12. Observability and operational UX

Retain the original posting, exact stock withdrawal, reason and actor. Use existing safe rejection and original request recovery controls. Explain when a receipt is ineligible or the stock is reserved.

### 13. Compatibility, migration, rollout, and rollback

Upgrade representative schema 28 data with purchases, a session, posted and pending receipts, a linked correction, a previous void and a historical reversal. Verify migration rollback, restart, and current and historical return receipts after activated restore.

### 14. Testing strategy and numeric budget

Minimum eight distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| State and UI | 1 | Observable scenarios in the case inventory. |
| Inventory projection | 1 | Observable scenarios in the case inventory. |
| Concurrency | 1 | Observable scenarios in the case inventory. |
| Recovery | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| Rejection | 1 | Observable scenarios in the case inventory. |
| Compatibility | 1 | Observable scenarios in the case inventory. |
| Workspace | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| receipt-return-C01 | State and UI | receipt-return-R1, receipt-return-R3 | Return an exact fractional receipt, retain its original posting and closed purchase amounts, and show the attributed return. |
| receipt-return-C02 | Inventory projection | receipt-return-R2, receipt-return-R3 | Record the exact withdrawal and recompute demand while respecting active reservations and an independent open purchase. |
| receipt-return-C03 | Concurrency | receipt-return-R2, receipt-return-R3 | Race two returns, identical keys, and a return against a correction. Verify one withdrawal. |
| receipt-return-C04 | Recovery | receipt-return-R2, receipt-return-R4 | Recover the original receipt after repeat, restart and activated restore, and reject a changed payload. |
| receipt-return-C05 | Authorization | receipt-return-R1, receipt-return-R4 | Reject missing or revoked grants, missing CSRF and foreign receipt identities. |
| receipt-return-C06 | Rejection | receipt-return-R1, receipt-return-R2, receipt-return-R3 | Reject stale, pending, untracked, open, canceled, corrected and returned receipts. A write failure rolls back the stock withdrawal. |
| receipt-return-C07 | Compatibility | receipt-return-R2, receipt-return-R4 | Migrate schema 28 data, preserve earlier evidence, roll back an interrupted upgrade and reject an inconsistent return link in a snapshot. |
| receipt-return-C08 | Workspace | receipt-return-R1, receipt-return-R3, receipt-return-R4 | Return a receipt from a closed session item and verify Shopping and Pantry in both locales and deployment modes on both image architectures. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [docs/operations.md](../docs/operations.md) · [docs/evidence/physical-receipt-return-qualification.md](../docs/evidence/physical-receipt-return-qualification.md) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [frontend/src/presentation/domus-shopping.ts](../frontend/src/presentation/domus-shopping.ts) · [frontend/tests/e2e/workspace-navigation.spec.ts](../frontend/tests/e2e/workspace-navigation.spec.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| docs/operations.md | update |
| docs/evidence/physical-receipt-return-qualification.md | create |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| frontend/src/presentation/domus-shopping.ts | update |
| frontend/tests/e2e/workspace-navigation.spec.ts | update |

### 16. Acceptance scenarios

Return four units from a closed purchase of four, verify the signed linked withdrawal and the resulting purchase need, then recover the original return receipt. Race a correction and return for the same receipt and verify stock is withdrawn once.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| receipt-return-R1 | receipt-return-C01, receipt-return-C05, receipt-return-C06, receipt-return-C08 |
| receipt-return-R2 | receipt-return-C02, receipt-return-C03, receipt-return-C04, receipt-return-C06, receipt-return-C07 |
| receipt-return-R3 | receipt-return-C01, receipt-return-C02, receipt-return-C03, receipt-return-C06, receipt-return-C08 |
| receipt-return-R4 | receipt-return-C04, receipt-return-C05, receipt-return-C07, receipt-return-C08 |

### 18. Implementation sequence

Add the return link and guarded transaction, expose the attributed histories, and qualify migration, recovery and the bilingual workspace.

### 19. Definition of Done

Keep 100 percent coverage globally and per authored file. Require CI, both actual image architectures, Copilot Verification and Bugbot on the same commit. Preserve installed Copilot resources. Releases and deployments require separate authorization.

### 20. References and decisions

Extends the purchase history and receipt invariants in shopping-management-R4, shopping-management-R5 and shopping-management-R6 after issue #84.

## Record the optional store on a household purchase session

- Status: Draft
- Owners: Domus maintainers and Shopping
- Scope: Store name entry and purchase-session history
- Open decisions blocking readiness: none

### 1. Executive summary

A shopping manager can record the store when saving a purchase session.
Members authorized to read purchase-session history can see it in the
list and detail.

### 2. Problem, current behavior, and evidence

Purchase sessions group a shopper, timestamp and multiple purchased items.
The Shopping specification includes optional store metadata. The current
session form and records contain no store field.

### 3. Actors, surfaces, and terminology

The authorized shopper records the trip from the current Shopping list.
The store is optional local text. The purchase session owns the shared
metadata for its existing item group.

### 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| purchase-session-store-R01 | A member with the current session recording grant can provide an optional store name as bounded local text in the existing purchase-session command. |
| purchase-session-store-R02 | Store metadata, purchase items and the original command receipt commit atomically. Replaying an original unnamed session retains its existing request identity. |
| purchase-session-store-R03 | Authorized session lists and details show the saved name or omit the label for an unnamed session. Existing purchase, receipt and stock quantities remain authoritative in their owning records. |
| purchase-session-store-R04 | Migrate and restore named and unnamed sessions with their identities, contents, and original receipts. |
| purchase-session-store-R05 | Show accessible English and Spanish form and history states. Preserve the entered name when a correctable error allows retry. |

The increment implements optional store metadata from shopping-management-R6.
Prices, refunds and additional lists have separate acceptance.

### 5. Current versus proposed product journey

Select at least two items for a trip. Enter a store if known and review the
session before recording it. Later open purchase sessions and verify the
store alongside the saved item group.

### 6. Functional behavior and state model

Apply the existing required-text validation to a supplied store name and
the existing 160-character product-label bound. An omitted store leaves an
unnamed session. Preserve the entered text in the review and receipt.
Omitting the field uses the original unnamed request shape and fingerprint.
A changed store under the same key conflicts.

### 7. User-facing configuration

The optional store is free text from the authorized shopper. It belongs to
the purchase session and uses the member's current UI language for labels.

### 8. Clean Architecture design

Shopping's domain value owns store validation. Application coordinates
the current grant, session write and receipt. SQLite persists and verifies
the optional column. The HTTP adapter exposes the typed request and views.
Use published ha-ui controls for entry, review and feedback.

### 9. UI/UX and content contract

Label the field Store (optional) in English and Tienda (opcional) in
Spanish. Show the exact entered name before recording and in the saved
session. Preserve a draft when quantity or text validation fails.
Use the existing session flow for an unnamed trip.

### 10. Failure, recovery, and cleanup

Roll back store metadata, items and receipt together on a failure.
Recover an already recorded session by its original key. Preserve a
correctable store draft in the form and show a specific field error.

### 11. Security, permissions, and privacy

Keep the existing Shopping read and session recording grants. Recheck
current authority for original operation recovery. Render the store as
inert text and scope all queries to the current household.

### 12. Observability and operational UX

The session history associates the name with the original shopper and
item group. Operational diagnostics use existing safe errors.

### 13. Compatibility, migration, rollout, and rollback

Migrate representative schema 30 sessions and schema 20 storage. A
previously recorded session remains unnamed, with its item links and
original operation recoverable. Verify a compatible rollback checkpoint
and the installed Edge candidate.

### 14. Testing strategy and numeric budget

Minimum six distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Store input | 1 | Observable scenarios in the case inventory. |
| Protected history | 1 | Observable scenarios in the case inventory. |
| Original operation | 1 | Observable scenarios in the case inventory. |
| Atomicity and concurrency | 1 | Observable scenarios in the case inventory. |
| Upgrade and restoration | 1 | Observable scenarios in the case inventory. |
| Browser and installed acceptance | 1 | Observable scenarios in the case inventory. |
| Total | 6 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| purchase-session-store-C01 | Store input | purchase-session-store-R01 | Record a named and an unnamed session. Reject overlong or invalid supplied text with the existing input preserved and no session written. |
| purchase-session-store-C02 | Protected history | purchase-session-store-R03 | Find the name in the authorized session list and detail with its original shopper and items. Verify unchanged stock and receipt quantities and current read denial. |
| purchase-session-store-C03 | Original operation | purchase-session-store-R02 | Recover a named session after a lost reply. Reuse the exact receipt for the same input and reject a changed name under the same key. Recover a previously recorded unnamed session with its original input. |
| purchase-session-store-C04 | Atomicity and concurrency | purchase-session-store-R02 | Inject a late failure and observe no new session, items or receipt. Compete for the same tracked purchase and verify only the winning session records its store. |
| purchase-session-store-C05 | Upgrade and restoration | purchase-session-store-R04 | Upgrade representative schema 30 and schema 20 data, preserving prior records. Restart and activate a compatible backup with a named session and recover its original operation. |
| purchase-session-store-C06 | Browser and installed acceptance | purchase-session-store-R05 | In English desktop and narrow Spanish views, enter a name, recover a correctable draft and find the recorded store in history. Verify both compositions, image architectures and the installed Edge version with disposable cleanup. |

### 15. Documentation and discoverability

[specs/shopping-management.md](shopping-management.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/user-guide.md](../docs/user-guide.md) · [backend/src/domus/domain/shopping.py](../backend/src/domus/domain/shopping.py) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/application/inventory\_queries.py](../backend/src/domus/application/inventory_queries.py) · [backend/src/domus/infrastructure/sqlite\_shopping.py](../backend/src/domus/infrastructure/sqlite_shopping.py) · [backend/src/domus/entrypoints/inventory\_http.py](../backend/src/domus/entrypoints/inventory_http.py) · [frontend/src/presentation/domus-inventory.ts](../frontend/src/presentation/domus-inventory.ts) · [frontend/src/presentation/inventory-messages.ts](../frontend/src/presentation/inventory-messages.ts)

| Path | Change |
|---|---|
| specs/shopping-management.md | update |
| docs/roadmap.md | update |
| docs/user-guide.md | update |
| backend/src/domus/domain/shopping.py | update |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/application/inventory_queries.py | update |
| backend/src/domus/infrastructure/sqlite_shopping.py | update |
| backend/src/domus/entrypoints/inventory_http.py | update |
| frontend/src/presentation/domus-inventory.ts | update |
| frontend/src/presentation/inventory-messages.ts | update |

### 16. Acceptance scenarios

Record a trip at a named store and find the name beside its item group.
Record another trip without a store. Verify current grants, original
operation recovery, atomicity, compatible data and both browser journeys.

### 17. Requirements traceability

| Requirement | Cases |
|---|---|
| purchase-session-store-R01 | purchase-session-store-C01 |
| purchase-session-store-R02 | purchase-session-store-C03, purchase-session-store-C04 |
| purchase-session-store-R03 | purchase-session-store-C02 |
| purchase-session-store-R04 | purchase-session-store-C05 |
| purchase-session-store-R05 | purchase-session-store-C06 |

### 18. Implementation sequence

Add the optional store value and migration, integrate the protected write
and history reads, then qualify the English and Spanish user journeys and
the Edge candidate.

### 19. Definition of Done

Pass the six cases, complete coverage and both architecture image checks.
Verify the installed Edge version and remove the disposable test data.

### 20. References and decisions

The existing Shopping contract defines optional stores and purchase-session
history under shopping-management-R6. Retain the published session and
physical receipt cases.
