# Add notes and priority to manual shopping requests

- Status: Draft
- Catalog capability: shopping-management

## 1. Executive summary

This bounded increment lets a household member add a plain-text note and priority to a manual extra for a catalog product or free-text item. The note defaults to empty; priority defaults to normal, with low, normal, high, and urgent available. Each request keeps its own annotation and attribution. Annotations remain inert display text and do not change quantities or the existing consolidation rules.

Member selects a product or enters a free-text item -> enters optional note and priority -> submits the existing manual-extra command -> sees the annotation with that request’s source details.

## 2. Problem, current behavior, and evidence

Household members need to distinguish variants and communicate urgency when requesting items. The issue describes this as a missing capability in manual extras; that description is issue-provided context, not proof of behavior in the selected revision.

The immutable owner `specs/shopping-management.md` defines a protected shared list with independent manual extras, catalog-product amounts or untracked named items, source attribution, and existing add/read permissions. The selected implementation’s `backend/src/domus/domain/shopping_needs.py` defines `ShoppingExtra` with identity, product/name, unit, quantity, member, creation time, and clearing fields; the selected `backend/src/domus/application/inventory.py` constructs it for the add-extra command. These observed definitions do not include note or priority fields. The owner is a prospective Draft, so it establishes the retained contract, not complete runtime acceptance evidence.

The delta adds annotation behavior while retaining the owner’s quantity, provenance, consolidation, permission, and receipt contracts. The owner requires `shopping.request` to add extras and `household.read` for the shared list; task source details continue to require `tasks.read` (`specs/shopping-management.md`, shared shopping list sections 3 and 11). Broader implementation status and any uninspected surfaces remain unverified.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
|---|---|---|---|
| Requester | Add an item-specific instruction and urgency while requesting an extra | Existing manual-extra flow for a catalog product or free-text item | Manual-extra form and shared Shopping list source details |
| Household reader | Understand each request without losing its source or quantity | Open the protected shared list and product source details | Consolidated product details or the free-text item |

A **manual extra** is an independently attributable shopping request. A **note** is optional plain text attached to that request. **Priority** is one of low, normal, high, or urgent, with normal as the default. A **source detail** identifies the individual request and its requester; a consolidated product line may contain multiple such requests. The retained owner `specs/shopping-management.md` remains authoritative for shopping quantities, source identity, permissions, pagination, and ordering. The companion defines only the annotation increment.

## 4. Goals, non-goals, and fixed invariants

Goals:

1. Allow both catalog-product and free-text manual extras to carry an optional note (empty by default) and priority (normal by default). Support at most 1,000 Unicode codepoints, preserve permitted multiline whitespace, reject invalid Unicode and unsupported control characters, and render notes as inert text.
2. Preserve each request’s exact quantity, requester, source identity, and independent annotation in source details. Keep free-text annotations directly visible; do not alter consolidation arithmetic, pagination, or ordering.
3. Retain existing authorization, command recovery, idempotency, atomicity, migration, and compatibility behavior while adding annotations, including legacy packets and receipts.
4. Provide a clearly labeled, bounded bilingual form with actionable validation and retained drafts, usable by keyboard and at 390 px touch width in both themes and both entry compositions.
5. Document the increment and its acceptance evidence while preserving the existing owner’s requirements and cases.

Non-goals: changing manual-extra quantities or consolidation; combining separate notes into a synthesized instruction; changing automatic demand, stock, purchase, or receipt effects; adding multiple-list management, money/currency, or editing existing extras; changing permissions; releasing Domus distributions or deploying Stable.

Fixed invariants: annotation input never grants authority. Additions retain `shopping.request`; list/source reads retain `household.read`; task-origin details require `tasks.read`; denied and cross-household callers gain no access. Notes are plain text, bounded and safe to display. Each annotation belongs to its original request and cannot mutate quantity, requester, or source identity. An unchanged original idempotency key returns its original result; changing an explicitly submitted annotation under that key conflicts without creating a second extra. Existing records, clients, receipts, and legacy pending packet payloads retain their original identities and default behavior. Extra, receipt, audit, and outbox effects remain atomic; current additive arithmetic, stock effects, and purchase effects remain unchanged. Migration must cover actual schemas 36 and 20, with restart, restoration, and compatible rollback behavior. Publication requires the specified format, internal and cross-document consistency, and reciprocal catalog ownership, paths, and evidence matching the generated view; those are outcomes to verify, not claims of completed checks.

| Requirement | Behavior |
| --- | --- |
| SDD-I157-U1-R1 | Manual extras for catalog products and free-text items accept an optional plain-text note defaulting to empty and priority defaulting to normal; supported priorities are low, normal, high, and urgent. Notes accept at most 1,000 Unicode codepoints, preserve permitted multiline whitespace, reject unsupported control characters and invalid Unicode, and render as inert text. |
| SDD-I157-U1-R2 | Each manual request retains its exact quantity, requester, source identity, and its own annotation. Consolidated product details show each request's annotation and attribution; free-text items expose their own note and priority. Annotations do not change quantities, invent combined instructions, or alter pagination and ordering. |
| SDD-I157-U1-R3 | Adding an extra retains the existing shopping.request permission; shopping list and source reads retain household.read, and task-origin details still require tasks.read. Denied and cross-household callers gain no authority. |
| SDD-I157-U1-R4 | The form uses the published exact shared ha-ui cohort, clear labels, defaults and limits, English and Spanish, actionable validation, and retained draft fields. It supports keyboard focus, both themes, both entry compositions, and actual narrow touch. After a lost response, the original command is recovered unchanged; checking an earlier outcome does not erase a later unrelated note or priority draft. |
| SDD-I157-U1-R5 | Existing clients, persisted active and cleared extras, and original receipts retain default behavior and original identities. Legacy pending packets are not rewritten to add defaults. An unchanged original key returns its original result; changing an explicitly submitted annotation under that key conflicts without creating another extra. |
| SDD-I157-U1-R6 | Extra creation, ordinary receipt, audit, and outbox effects remain atomic across concurrent attempts and injected failures. Migration works from actual schemas 36 and 20 and retains restart, restoration, and compatible rollback behavior. Existing automatic and manual additive arithmetic, stock effects, and purchase effects remain unchanged. |
| SDD-I157-U1-R7 | The bounded companion documents the delivered increment and is linked from the catalog. The owning contract, qualification map, user documentation, and closed HTTP contracts describe the increment while preserving original owning requirements, cases, aliases, and reverse mappings. Native admission owns requirement and case identities; evidence distinguishes completed bounded-increment evidence from remaining broader Shopping capability. |
| SDD-I157-U1-R8 | Acceptance evidence covers complete global and per-file coverage, compiled Ingress and standalone builds, both CPU images, installed Edge acceptance, and scoped cleanup. Domus distribution releases and Stable deployment remain outside this increment. |

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User effect |
|---|---|---|---|
| Enter a manual request | The retained Shopping contract covers manual demand but does not define notes or priority for a manual extra. | A member enters a catalog product or free-text item, exact quantity, optional note, and priority. The note defaults to empty; priority defaults to normal. | The request keeps its product or free-text identity and exact quantity while carrying its own instructions and urgency. |
| Validate and submit | The retained owner governs shopping demand, authorization and durable operation behavior. | Validate the note and priority, then submit using the existing manual-extra command and permission boundary. | Invalid input is explained while draft fields remain available for correction. |
| Review the list | Consolidated lines retain their individual demand sources. | Product details show each manual request’s note, priority, requester, source identity and quantity independently. A free-text item exposes its own note and priority. | Members can distinguish independent requests without combining their instructions or changing quantities, pagination or ordering. |
| Recover a submission | The owner defines original-operation receipt and duplicate behavior. | Following a lost response, recover or resend the original command unchanged; keep unrelated annotation drafts entered afterward. | Recovery does not create another extra or discard later edits. |

Text equivalent: enter a manual catalog or free-text request and its annotations -> validate and submit under existing authorization -> review annotations with their source details -> recover the same operation after a lost response. The existing shopping contract and cases in `specs/shopping-management.md` remain authoritative; this companion adds only the bounded manual annotation behavior.

## 6. Functional behavior and state model

A manual extra may be for a catalog product or a free-text item. Each extra retains its exact quantity, requester, source identity and its own note and priority. Notes are plain text, default to empty, and accept at most 1,000 Unicode codepoints. Preserve permitted multiline whitespace; reject unsupported control characters and invalid Unicode. Render note content as inert text. Priority defaults to normal and is one of low, normal, high or urgent.

Annotations belong to the individual manual request. Consolidation may group compatible product demand under the retained owner’s rules, but product details must expose each contributing manual request’s annotation and attribution. A free-text item exposes its own note and priority. Do not derive combined instructions, change demand arithmetic or exact quantities, or alter existing pagination and ordering.

Adding an extra retains `shopping.request`; shopping list and source reads retain `household.read`; task-origin details continue to require `tasks.read`. Denied and cross-household callers gain no authority. Preserve existing automatic and manual additive arithmetic, stock effects and purchase effects.

A replay with the unchanged original key and payload returns its original result. If an explicitly submitted annotation changes under that key, report a conflict and create no extra. Do not rewrite legacy pending packets to insert defaults. Creation, ordinary receipt, audit and outbox effects remain atomic under concurrent attempts and failures. Existing schema migration, restart, restoration and compatible rollback behavior must preserve extras and receipts.

## 7. User-facing configuration

There is no additional user-configurable policy in this increment. The annotation inputs have fixed defaults and bounds: note is empty or plain text of at most 1,000 Unicode codepoints; priority is normal by default and limited to low, normal, high or urgent. Validation rejects invalid Unicode, unsupported control characters and over-limit notes while retaining draft fields. These limits, inert rendering and existing authorization rules cannot be weakened by configuration.

The form must use the published exact shared ha-ui cohort, clear labels and limits, actionable validation, and English and Spanish content. Both manual-entry compositions must support keyboard focus, light and dark themes, and actual 390 px touch use. Retrying after a lost response uses the original command unchanged; checking an earlier outcome must preserve any later unrelated note or priority draft.

## 8. Clean Architecture design

Keep annotation policy with the existing shopping domain and application command boundaries described by `specs/shopping-management.md`. The domain owns note validation, the supported priority set and per-request annotation invariants. The application command carries the manual request identity and annotations while preserving the existing authorization, receipt and idempotency semantics. Persistence and transport adapters map the added fields without introducing alternate business rules or provider-specific types into domain policy. Presentation owns localized labels, retained form drafts, actionable validation and inert rendering; it does not own authorization or consolidation arithmetic.

The durable extra, ordinary receipt, audit and outbox effects must share the owner’s atomic operation boundary. Migration from actual schemas 36 and 20, restart, restoration and compatible rollback must retain existing records and receipts. Legacy pending packet payloads remain unchanged; absent annotations resolve to empty note and normal priority without changing original identities. Concurrent attempts and injected failures must not leave partial effects.

Architecture and acceptance evidence must establish the required domain, command, adapter, persistence, presentation and migration behavior, including both entry compositions and authorization boundaries. The inspected specification standard and retained owner do not establish a concrete installed invocation for these checks; concrete command and prerequisite remain unverified.

## 9. UI/UX and content contract

### 9.1 Manual request form and source details

The companion extends the retained Shopping contract in `specs/shopping-management.md` only for annotations on manual extras. Both catalog-product and free-text forms provide a clearly labeled optional note and priority. The note defaults to empty; priority defaults to Normal. Offer Low, Normal, High, and Urgent with text labels that do not rely on color. Explain the 1,000 Unicode-codepoint note limit and that permitted line breaks and whitespace are preserved. Inline validation identifies the field and gives a corrective action; a rejected value leaves the other entered fields intact. The note is displayed as inert text, including when it contains markup-like or command-like characters.

For a consolidated catalog product, source details show each manual request separately with its exact quantity, requester, source identity, note, and priority. Do not merge annotations into a combined instruction or let them affect consolidation arithmetic, pagination, or ordering. A free-text request exposes its own note and priority with the same attribution and quantity clarity. For example: “Tea · 2 packs · Requested by Ana · High · Decaffeinated” describes one source request; a second request remains separately identifiable.

### 9.2 Accessible content and interaction

Use the exact published shared `ha-ui` cohort. Both manual-entry compositions must have programmatically associated labels, announced limits and validation, logical keyboard order, visible focus, and retained draft fields. The form and source details must work in English and Spanish, in both light and dark themes, and at an actual 390 px touch width. At narrow widths, labels and values remain readable without requiring color, hover, or horizontal scrolling. Verify focus behavior and touch operation on the rendered interface, not only from component structure. Localization must preserve the meaning of defaults, limits, priorities, and recovery actions.

### 9.3 Recovery content

After a request is submitted, show whether it is still being sent, its confirmed result, or that the result is unknown and needs recovery. Keep the primary action explicit. If the response is lost, offer recovery of the original command; do not silently change its note, priority, quantity, or identity. If the member has since entered an unrelated draft, resolving the earlier outcome must leave that draft intact. The existing owner remains authoritative for the broader Shopping journey and presentation contract.

## 10. Failure, recovery, and cleanup

### 10.1 Validation and request outcomes

Invalid note input—including more than 1,000 Unicode codepoints, invalid Unicode, or unsupported control characters—must identify the note field, explain the limit or correction, preserve other draft fields, and produce no extra or receipt. Empty note and omitted priority use their stated defaults. Permission denial and cross-household access reveal no request or source details and do not create effects.

### 10.2 Retry, replay, and partial failure

A lost response leaves the outcome uncertain to the client; recovery checks or resends the original command unchanged. An unchanged original idempotency key returns its original result. If an explicitly submitted annotation differs under that key, report a conflict and create no second extra. Checking an earlier result must not overwrite a later unrelated note or priority draft. Existing pending packets and original receipts retain their payload and identity; recovery must not rewrite a legacy packet to inject defaults.

Extra creation, ordinary receipt, audit, and outbox effects form one atomic outcome under concurrent attempts and injected failures. On failure at any of these effects, report whether the operation committed or remains recoverable based on durable evidence; never imply success from a partial write. Retries must be safe and bounded by the existing operation recovery behavior. No special cleanup may erase committed shopping, receipt, audit, or outbox facts. Tests must exercise concurrent attempts and failures at each effect boundary, confirming either all required effects or none.

## 11. Security, permissions, and privacy

### 11.1 Authorization and household isolation

Adding a manual extra continues to require `shopping.request`. Shopping list and source reads continue to require `household.read`; task-origin details continue to require `tasks.read`. Enforce authorization at the backend boundary for each operation and its current household scope. A denied caller or caller from another household gains no new ability to add, read, infer, or recover another household’s requests. UI visibility is not an authorization control.

### 11.2 Input and privacy boundaries

Treat note text as untrusted input at every transport, persistence, and rendering boundary. Validate Unicode and reject unsupported controls without silently changing accepted text. Encode output as inert text; do not interpret it as HTML, Markdown, a URL, a command, or an instruction. Keep attribution and source identity scoped to the authorized household. Operational evidence may identify safe failure categories and correlation needed for recovery, but must not expose credentials or unrelated household data. Security acceptance includes hostile text rendering, invalid input, denied operations, cross-household reads and writes, and protected task-origin details.

## 12. Observability and operational UX

### 12.1 Member-facing status

Show a concise state for submission and recovery: sending, saved with the original receipt, conflict requiring review, denied, or outcome unknown and recoverable. State the retained facts and the single next action where action is needed. Keep the note and priority visible in the relevant source detail after a confirmed save. Do not create duplicate activity or notifications when an unchanged command is replayed.

### 12.2 Operator evidence

Record enough sanitized evidence to distinguish validation rejection, authorization denial, idempotent replay, changed-payload conflict, storage failure, and successful completion. Correlate extra, ordinary receipt, audit, and outbox effects so atomicity and recovery can be investigated. Avoid logging raw note text by default; diagnostics must not include secrets or unrelated personal data. Evidence for the bounded increment must distinguish completed checks for annotations from any broader Shopping capability that remains unverified. Metrics or logs are supporting operational evidence, not proof that a scenario passed.

## 13. Compatibility, migration, rollout, and rollback

### 13.1 Compatibility and migration

Existing clients that omit annotations continue to create manual extras with an empty note and Normal priority. Persisted active and cleared extras and original receipts retain their existing behavior and identities. Preserve legacy pending packets and their payload fingerprints byte-for-byte; do not rewrite them to add defaults. An unchanged original key returns its original result, while a changed explicitly submitted annotation under that key conflicts without creating another extra.

Migration acceptance must use actual schema 36 and schema 20 data, then verify restart, restoration, and compatible rollback while preserving existing extras and receipts. A rollback must not reinterpret newer data silently or alter the established shopping arithmetic. Existing automatic and manual additive calculations, stock effects, and purchase effects remain unchanged.

### 13.2 Delivery and rollback evidence

Before claiming acceptance, collect evidence for complete global and per-file coverage, compiled Ingress and standalone builds, both CPU images, installed Edge acceptance, and scoped cleanup. The concrete invocation and prerequisites for each check remain unverified here; do not treat a declaration or command name as execution or a passing result. Cleanup must be limited to resources owned by this acceptance run and must preserve durable business records. Domus distribution releases and Stable deployment are outside this increment. Rollback evidence must establish compatible code and data restoration without changing original identities or losing committed effects.

## 14. Testing strategy and numeric budget

Minimum budget: ten distinct acceptance cases, one for each newly defined case in this companion’s inventory. Repeated runs, locales, input rows, image architectures, or build configurations do not increase the distinct-case count unless they exercise a separately defined observable behavior. The budget covers annotation defaults, supported values and invalid boundaries; independent source attribution and unchanged consolidation; authorization; form accessibility and localization; replay and legacy compatibility; idempotency conflicts; atomicity and concurrency; schema migration and recovery; publication consistency; and delivery evidence. The inventory’s ten rows are the counted cases; existing shopping-management cases remain references and are not recounted.

Acceptance evidence must exercise both catalog-product and free-text requests, including the 1,000-codepoint boundary, multiline text, invalid Unicode and unsupported controls, inert rendering, exact quantities, source attribution, and unchanged pagination and ordering. It must cover authorized, denied and cross-household access; both entry compositions; keyboard focus, both themes, English and Spanish, retained drafts, and actual 390 px touch. Replay, changed-payload conflict, concurrent attempts, injected failures, original receipts, legacy pending packets, and migration from actual schemas 36 and 20 must be evidenced along with restart, restoration and compatible rollback. Existing automatic and manual arithmetic, stock effects and purchase effects must remain unchanged.

Keep complete global and per-file coverage. Evidence must include compiled Ingress and standalone builds, both CPU images, installed Edge acceptance and scoped cleanup. Use deterministic fixtures for boundary, replay, race and failure behavior; coverage counts do not establish semantic completeness or executed acceptance. The selected root `package.json` declares pnpm 10.34.0 and Node 24.20.x and exposes `pnpm test` and `pnpm test:architecture`; their concrete definitions are in that file. No selected-source invocation or referenced definition was verified for the requested compiled Ingress/standalone builds, both CPU images, installed Edge acceptance, or scoped cleanup, so their concrete invocations and prerequisites remain unverified. Do not substitute documentation validation for SDK consistency verification.

Publication acceptance must explicitly observe all three outcomes: the specification satisfies the required format; internal and cross-document consistency is checked; and reciprocal catalog ownership, paths and evidence agree with the generated view. The concrete invocation or prerequisite for checking those outcomes remains unverified in this selected source.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| domain | 1 | Observable scenarios in the case inventory. |
| presentation | 2 | Observable scenarios in the case inventory. |
| permissions | 1 | Observable scenarios in the case inventory. |
| replay | 1 | Observable scenarios in the case inventory. |
| idempotency | 1 | Observable scenarios in the case inventory. |
| atomicity | 1 | Observable scenarios in the case inventory. |
| migration | 1 | Observable scenarios in the case inventory. |
| publication | 1 | Observable scenarios in the case inventory. |
| delivery | 1 | Observable scenarios in the case inventory. |
| Total | 10 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| shopping-manual-annotations-C01 | domain | SDD-I157-U1-R1 | Submit empty/default annotations and each supported priority for catalog-product and free-text manual extras; verify note length at 1,000 Unicode codepoints, permitted multiline preservation, rejected over-limit, invalid-Unicode and unsupported-control inputs, and inert rendering of untrusted text. |
| shopping-manual-annotations-C02 | presentation | SDD-I157-U1-R1, SDD-I157-U1-R2 | Create multiple requests for the same catalog product and verify each request's note, priority, requester, source identity and exact quantity appear independently in source details; verify free-text item annotation and unchanged consolidation arithmetic, pagination and ordering. |
| shopping-manual-annotations-C03 | permissions | SDD-I157-U1-R3 | Verify authorized add/read paths retain shopping.request, household.read and task-origin tasks.read requirements; denied and cross-household callers receive no new authority or data. |
| shopping-manual-annotations-C04 | presentation | SDD-I157-U1-R4 | Exercise both manual-extra entry compositions with the exact shared ha-ui cohort, labels, defaults, limits, actionable validation, retained fields, EN/ES content, keyboard focus, both themes and actual 390 px touch. |
| shopping-manual-annotations-C05 | replay | SDD-I157-U1-R4, SDD-I157-U1-R5 | After a lost response, recover and resend the original command unchanged; verify checking an earlier outcome preserves a later unrelated note/priority draft, and legacy pending packets and original receipts retain their identities and default behavior. |
| shopping-manual-annotations-C06 | idempotency | SDD-I157-U1-R5 | Replay an unchanged original key and verify its original result; submit a changed explicit annotation with that key and verify conflict without another extra. |
| shopping-manual-annotations-C07 | atomicity | SDD-I157-U1-R6 | Race concurrent attempts and inject failures at extra, receipt, audit and outbox effects; verify all effects commit or roll back atomically and existing arithmetic, stock and purchase effects remain unchanged. |
| shopping-manual-annotations-C08 | migration | SDD-I157-U1-R6 | Migrate actual schema 36 and schema 20 data, then verify restart, restoration and compatible rollback preserve existing extras and receipts. |
| shopping-manual-annotations-C09 | publication | SDD-I157-U1-R7 | Verify the companion and catalog link describe the bounded increment, preserve owning identities and reverse mappings, align the owning contract, qualification map, user documentation and closed HTTP contracts, and separate completed increment evidence from broader remaining capability. |
| shopping-manual-annotations-C10 | delivery | SDD-I157-U1-R8 | Verify complete global and per-file coverage, compiled Ingress and standalone builds, both CPU images, installed Edge acceptance and scoped cleanup; confirm release and Stable deployment are outside the increment. |

## 15. Documentation and discoverability

This companion records only the manual-request note and priority increment for the existing Shopping capability. Keep `specs/shopping-management.md` as the owning contract and retain its requirements, cases, aliases and reverse mappings. The companion is a prospective create at `specs/shopping-manual-annotations.md`; that path is not asserted to exist in the selected source. Its inventory supplies the single navigation source for the host to project links. Link the companion from the Shopping catalog and reconcile the catalog’s ownership, paths and evidence with its generated view.

Update the owning contract, qualification map, user documentation and closed HTTP contracts to describe the delivered increment while preserving their existing identities and reverse mappings. User guidance should explain optional notes, the normal-priority default, the four priorities, the 1,000-codepoint limit, inert text rendering and how independent requests appear in source details. Include English and Spanish labels, defaults, limits and actionable validation. Operator and contributor guidance should explain replay behavior, compatibility for existing clients and receipts, and the evidence for migration, recovery and atomic effects. Distinguish completed evidence for this bounded increment from evidence still needed for the broader Shopping capability.

The selected catalog registers evidence paths but is not a complete file inventory. No concrete qualification-map, user-documentation, or closed HTTP-contract path for this increment is asserted here; their selected-source locations and update evidence remain unverified.

| Path | Change |
| --- | --- |
| specs/shopping-manual-annotations.md | create |

[specs/shopping-manual-annotations.md](shopping-manual-annotations.md)

## 16. Acceptance scenarios

1. Submit catalog-product and free-text manual requests with omitted annotations, an empty note, and each supported priority. Observe an empty-note and normal-priority default, exact quantities and identities, and inert rendering. Accept a note at 1,000 Unicode codepoints with permitted multiline whitespace; reject an over-limit note, invalid Unicode and unsupported controls with actionable feedback. See `shopping-manual-annotations-C01`.
2. Create multiple requests for one catalog product. In consolidated source details, observe each request’s own note, priority, requester, source identity and exact quantity. Observe the free-text item’s own note and priority, with arithmetic, pagination and ordering unchanged. See `shopping-manual-annotations-C02`.
3. Use the existing add and read permissions, including task-origin detail access. A denied or cross-household caller gains no authority or data. See `shopping-manual-annotations-C03`.
4. Use both manual-extra entry compositions with the exact shared ha-ui cohort. Observe clear labels, defaults and limits, English and Spanish content, actionable validation, retained fields, keyboard focus, both themes and actual 390 px touch. See `shopping-manual-annotations-C04`.
5. After a lost response, recover and resend the original command unchanged. Checking an earlier outcome preserves a later unrelated note and priority draft. Existing receipts and legacy pending packets retain their identities and default behavior. See `shopping-manual-annotations-C05`.
6. Replay an unchanged original key and observe its original result. Change an explicitly submitted annotation under that key and observe a conflict without a second extra. See `shopping-manual-annotations-C06`.
7. Race concurrent attempts and inject failures at extra, receipt, audit and outbox effects. Observe atomic commit or rollback and unchanged arithmetic, stock and purchase effects. See `shopping-manual-annotations-C07`.
8. Migrate actual schema 36 and schema 20 data, then restart, restore and perform compatible rollback. Observe existing extras and receipts preserved. See `shopping-manual-annotations-C08`.
9. Verify the companion and catalog link, preserved owning identities and reverse mappings, aligned owning contract, qualification map, user documentation and closed HTTP contracts, and evidence that distinguishes this completed increment from broader remaining capability. See `shopping-manual-annotations-C09`.
10. Observe complete global and per-file coverage, compiled Ingress and standalone builds, both CPU images, installed Edge acceptance and scoped cleanup; confirm Domus distribution releases and Stable deployment are outside this increment. See `shopping-manual-annotations-C10`.

## 17. Requirements traceability

Each requirement must map only to inventory cases that exercise its behavior. The inventory is the source of the case definitions; existing owner cases remain references.

- `SDD-I157-U1-R1` is exercised by `shopping-manual-annotations-C01` and `shopping-manual-annotations-C02`.
- `SDD-I157-U1-R2` is exercised by `shopping-manual-annotations-C02`.
- `SDD-I157-U1-R3` is exercised by `shopping-manual-annotations-C03`.
- `SDD-I157-U1-R4` is exercised by `shopping-manual-annotations-C04` and `shopping-manual-annotations-C05`.
- `SDD-I157-U1-R5` is exercised by `shopping-manual-annotations-C05` and `shopping-manual-annotations-C06`.
- `SDD-I157-U1-R6` is exercised by `shopping-manual-annotations-C07` and `shopping-manual-annotations-C08`.
- `SDD-I157-U1-R7` is exercised by `shopping-manual-annotations-C09`.
- `SDD-I157-U1-R8` is exercised by `shopping-manual-annotations-C10`.

| Requirement | Cases |
|---|---|
| SDD-I157-U1-R1 | shopping-manual-annotations-C01, shopping-manual-annotations-C02 |
| SDD-I157-U1-R2 | shopping-manual-annotations-C02 |
| SDD-I157-U1-R3 | shopping-manual-annotations-C03 |
| SDD-I157-U1-R4 | shopping-manual-annotations-C04, shopping-manual-annotations-C05 |
| SDD-I157-U1-R5 | shopping-manual-annotations-C05, shopping-manual-annotations-C06 |
| SDD-I157-U1-R6 | shopping-manual-annotations-C07, shopping-manual-annotations-C08 |
| SDD-I157-U1-R7 | shopping-manual-annotations-C09 |
| SDD-I157-U1-R8 | shopping-manual-annotations-C10 |

## 18. Implementation sequence

1. Review the bounded increment against the immutable retained owner, `specs/shopping-management.md`, preserving its requirements, cases, aliases, and reverse mappings. Resolve any readiness-blocking decisions before implementation.
2. Define and test annotation value rules and compatibility behavior: empty-note and normal-priority defaults, the four allowed priorities, the 1,000-codepoint limit, permitted multiline whitespace, invalid Unicode and control-character rejection, and inert rendering.
3. Extend the manual-extra command and its transport, journal, persistence, receipt, audit, and outbox paths while retaining exact quantity, requester, source identity, permission checks, unchanged-key replay, changed-payload conflict, and atomicity under races and failure.
4. Implement source-level presentation for catalog-product and free-text requests, including independent attribution and annotations, unchanged consolidation, pagination, and ordering. Add the shared ha-ui cohort, English and Spanish content, actionable validation, retained drafts, keyboard behavior, both themes, and actual 390 px touch evidence.
5. Establish migration, restart, restoration, and compatible rollback evidence from actual schemas 36 and 20. Preserve legacy pending packets, original receipts, and existing arithmetic, stock, and purchase effects.
6. Update the owning contract, qualification map, user documentation, and closed HTTP contracts for the delivered increment without rewriting retained owner identities. Add the companion and reciprocal catalog ownership/evidence metadata, then verify the generated catalog view.
7. Complete behavior, compatibility, security, publication, and delivery acceptance. Record the exact evidence and cleanup for the bounded Edge acceptance; do not extend this increment to Domus distribution releases or Stable deployment.

## 19. Definition of Done

- [ ] Every annotation behavior is covered: defaults and all supported priorities; both manual-extra kinds; length, whitespace, invalid input, and inert rendering; independent source attribution; and unchanged quantities, consolidation, pagination, and ordering.
- [ ] Permission and privacy acceptance confirms `shopping.request`, `household.read`, and task-origin `tasks.read` remain in force, with denied and cross-household callers gaining no authority or data.
- [ ] UI acceptance covers both entry compositions, the exact shared ha-ui cohort, labels, limits, English and Spanish, actionable validation, retained fields, keyboard focus, both themes, and actual 390 px touch. Lost-response recovery resends the original command unchanged, and an earlier outcome check preserves a later unrelated draft.
- [ ] Compatibility and replay acceptance preserves existing clients, active and cleared extras, original receipts, and legacy pending packet identities and default behavior. An unchanged original key returns its original result; a changed explicitly submitted annotation conflicts without creating another extra.
- [ ] Concurrent attempts and injected failures prove extra, ordinary receipt, audit, and outbox effects commit or roll back atomically. Existing automatic and manual additive arithmetic, stock effects, and purchase effects remain unchanged.
- [ ] Migration, restart, restoration, and compatible rollback are evidenced against actual schemas 36 and 20 while preserving existing extras and receipts.
- [ ] Each requirement has a concrete accepting case, each case maps only to requirements it exercises, and all admitted case identities and assertions are retained. Derived counts or reciprocal mappings are not treated as semantic completeness or executed acceptance.
- [ ] The specification satisfies the required format; internal and cross-document consistency is checked; reciprocal catalog ownership, paths, and evidence agree with the generated view. These are observable publication outcomes, not generic maintainer acceptance or source-claim review.
- [ ] The bounded companion is linked from the catalog, and the owning contract, qualification map, user documentation, and closed HTTP contracts describe the increment while preserving original owner requirements, cases, aliases, and reverse mappings. Evidence distinguishes completed bounded-increment evidence from remaining broader Shopping capability.
- [ ] Delivery evidence covers complete global and per-file coverage, compiled Ingress and standalone builds, both CPU images, installed Edge acceptance, and scoped cleanup. Domus distribution releases and Stable deployment remain outside this increment.
- [ ] Concrete repository validation invocations and prerequisites remain unverified. The repository standard names `pnpm run validate:specifications` and `pnpm run generate:specifications` in `specs/README.md`, but those scripts are not declared in the inspected root `package.json`; do not report them as runnable or passing without verification. Command declaration alone is not execution or acceptance.

## 20. References and decisions

Primary source: [Issue #157](https://github.com/vypdev/domus/issues/157). The bounded change is one part of the existing `shopping-management-R1` contract; retain the immutable owner `specs/shopping-management.md` and its cases rather than restating or replacing them.

The prospective companion is `specs/shopping-manual-annotations.md`. The selected catalog view registers `shopping-management` with `specs/shopping-management.md`; this draft therefore requires reciprocal companion ownership and evidence to be added and checked in the generated view. The selected repository standard is `specs/README.md` and its template is `specs/_template.md`.

Confirmed scope decisions: annotations belong to each manual source; defaults are an empty note and normal priority; priorities are low, normal, high, and urgent; notes are limited to 1,000 Unicode codepoints and render as inert text. Editing existing extras, multiple-list management, money and currency, replacing blocked work for issue #154, and resolving the pending owner decision for issue #90 are outside this increment. Distribution releases and Stable deployment are also outside scope.

The root `package.json` declares pnpm 10.34.0 and does not declare the specification validation or generation scripts named in `specs/README.md`. Their executable definitions and prerequisites were not verified; the concrete invocation remains unverified. No command execution or implementation acceptance is claimed.
