# Household administration workspace

- Status: Draft
- Date: 2026-11-02
- Catalog capability ID: household-identity (companion)
- Last verified: not applicable; this is a prospective specification.
- Owners: Domus maintainers (catalog review assignment pending)
- Scope: Complete the already specified household administration application, protected API, and workspace on the actual merged schema9 baseline.
- Related issues/PRs: [Issue #25](https://github.com/vypdev/domus/issues/25); PR #24 is the merged storage checkpoint described by the supplied evidence.
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: None identified. Implementation and acceptance remain outstanding; Draft status and the Action-owned managed-branch readiness gate remain in force.

This companion adds implementation scope under the existing household-identity capability. It does not replace or reduce `specs/household-identity.md`, `specs/household-administration.md`, or `specs/household-administration-integration.md`. Preserve all HADM-01..HADM-08 requirements and all 72 existing `household-admin-C01` through `household-admin-C72` cases, as well as all eight `household-admin-integration-C01` through `household-admin-integration-C08` refinements and the household-identity and delivery-quality contracts. Those retained cases and refinements are existing owner inventory, not cases in this companion's budget. Owning inventory, workspace refinement rows and parameterized executions must not be added together as independently completed product journeys. A merged checkpoint, this draft, or publication does not establish workspace acceptance.

## 1. Executive summary

Complete the household administration workspace in native HA Ingress and standalone deployments. Verified participants can review current identity and access, edit their permitted public alias, and manage their own private preferences. Current administrators can use the existing household, membership, profile, and mapping rules through accessible forms. Canonical Home Assistant identity, current authority, original-operation evidence, and honest provider facts remain authoritative.

Recommended defaults are no saved alias, browser locale falling back to English, routine summaries enabled as a stored preference, and an empty separate administration journal. Every write and disclosure of an original result requires current authority. Private preference values and inferable private payload/result fingerprints never enter shared audit, events, logs, or roster data.

```text
Verified entry -> current authorized facts -> explicit revision-bound action -> atomic original operation -> protected receipt and refreshed current state
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Participants need to understand which verified household identity and permissions apply, and to manage public presentation and private preferences safely. Administrators need complete forms for existing household, membership, permission-profile, and mapping operations without bypassing current authorization or last-effective-administrator safeguards. Both deployment modes need equivalent accessible behavior and truthful recovery after races, lost responses, or restoration.

### 2.2 Current behavior

1. Supplied immutable evidence identifies actual PR #24 merge baseline `6d84d4815a8bbfe071979df6650d01e433dcc2db`, reviewed head `4e59e04d956668c76f3c8d48e824059fd205d661`, and independently verified exact tree equality.
2. That checkpoint implements schema9 profile storage, separate public/private repositories and revisions, atomic member defaults, strict decoding/CAS/FKs, schema1..8 upgrades, and independent checkpoint profile validation.
3. The checkpoint exposes no new administration HTTP surface and does not complete the workspace or the retained 72-journey acceptance contract.
4. The issue reports backend coverage and both-CPU image/product-suite results for the storage checkpoint. These are baseline evidence only, not execution of this companion's cases or the retained workspace cases.

### 2.3 Evidence

- Code/workflow/documentation references: the selected immutable source is `https://github.com/vypdev/domus/tree/6d84d4815a8bbfe071979df6650d01e433dcc2db`; the supplied catalog records existing household identity entrypoints, code, tests, and documentation. Existing owner specifications are `specs/household-identity.md`, `specs/household-administration.md`, and `specs/household-administration-integration.md`.
- Incidents or concrete examples: the issue reports PR #24 as storage-only and explicitly distinguishes checkpoint results from complete administration acceptance. It also records prior publication response-size failures; this companion is the supported new companion route.
- External primary sources: none required to resolve product policy. Provider behavior must be verified against actual supported Home Assistant sources during implementation.
- Unknowns: precise provider availability/denial behavior until verified against the supported source; implementation details and test outcomes for all proposed workspace behavior.

### 2.4 Retrospective classification (as-built baselines only)

Not applicable: this is a prospective companion, not a reconstruction of an implemented workspace. Section 2.2 records only the supplied checkpoint facts; proposed behavior is not represented as current.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
|---|---|---|---|
| Verified participant | Review current identity/access and manage permitted own alias and preferences | Existing verified HA session | Ingress or standalone workspace, forms, status and recovery views |
| Current household administrator | Review roster and manage permitted existing household/member/profile/mapping state | Current-authorized administration workspace | Roster, pending review, settings, ordinary profile and mapping forms |
| Operator | Understand original processing, restoration, and compatible rollback | Existing owned-storage and operations tools | Sanitized evidence and operator documentation |

Canonical HA user ID establishes identity. A display name, Domus alias, or avatar is inert presentation, not identity or permission. Locale and routine-summary choice are owner-private preferences. An original receipt describes original processing; it does not establish current grants or current effects. Technical event/outbox dispatch is not notification delivery. Provider unavailable, denied, and confirmed absence are distinct facts.

## 4. Goals

| Requirement | Behavior |
|---|---|
| HADW-01 | Provide currently authorized public-alias commands and queries with independent revision and immutable original-operation key/payload semantics. |
| HADW-02 | Provide owner-only preference commands, queries, and original-result disclosure; prevent private values and inferable private payload/result fingerprints from shared surfaces. |
| HADW-03 | Expose bounded, verified HA name/avatar and directory facts, distinct from identity and permission authority; preserve unavailable, denied, and confirmed-absence states. |
| HADW-04 | Integrate existing household/member/settings/profile/mapping operations and last-effective-administrator safeguards into explicit, current-authorized forms. |
| HADW-05 | Provide protected closed HTTP DTOs, session CSRF/Origin/context validation on every write and original POST replay, protected existing GET result lookup, and a separate bounded journal with exact revisions and context/lifecycle fencing. |
| HADW-06 | Deliver complete accessible EN/ES administration behavior in native Ingress and standalone deployments, including inert rendering and honest save-with-delivery-unavailable status. |
| HADW-07 | Preserve actual schema9, immutable schema1..8 inputs, operation/history and recurrence state, restoration, and compatible runtime rollback without relabeling schema or fabricating migration history. |
| HADW-08 | Preserve all owning contracts and case inventories; deliver tests-first Clean Architecture, full supported global and per-authored-module coverage, actual both-CPU package/runtime acceptance, and user/setup/operator/contributor/migration documentation. |

### Non-goals

No gateway or Copilot modification, arbitrary remote images/uploads, person-based authentication, notification-delivery claim, new household policy, new DDL, release/tag/HA rollout, or acceptance of recurrence/calendar issue #23. No retained requirement or case is removed. Owner HA Edge.5/schema7, current rollback, Stable/Edge/all-domain release controls, and gateway integration remain separate unchanged controls.

### Fixed invariants

Current authority precedes every effect and original-result disclosure. Expected-revision comparison and immutable original key/payload handling are atomic under concurrent writes. No automatic mutation retry, key replacement, stale-dialog rebase, or private preference disclosure to another administrator is permitted. HTTP and journal formats are closed. Exact revision transport must not round unsafe numeric values. Application work does not change schema9 or frozen schema1..8 inputs.

## 5. Current versus proposed product journey

| Stage | Current | Proposed | User/operator effect |
|---|---|---|---|
| Entry | Existing verified setup/join and partial identity APIs | Open the current-authorized workspace | See which current identity and household context is active |
| Review | Checkpoint profile storage exists; complete roster/workspace is absent | Review masked roster, honest source states, permissions, own private preferences, and permitted forms | Understand verified facts, missing facts, and pending review |
| Change | Complete administration commands/forms are absent | Human confirms a closed, revision-bound action under current authority | Stale or denied changes produce no new effect and preserve a safe draft |
| Recover | Existing original-operation owners remain authoritative | Use the separate bounded administration journal and protected original-result lookup | Recover the same original operation without replacing or replaying mutation intent |

```mermaid
flowchart LR
    A[Verified session] --> B[Current authority and permitted facts]
    B --> C[Explicit revision-bound form]
    C --> D[Authorized atomic operation]
    D --> E[Original receipt and refreshed current state]
```

Text equivalent: verified session -> current authority and permitted facts -> explicit revision-bound form -> authorized atomic operation -> original receipt and refreshed current state.

## 6. Functional behavior and state model

### 6.1 Happy path

1. Derive principal, installation, household, and current context from the trusted existing session boundary; never accept a client-selected principal.
2. Read permitted local state. Obtain bounded provider facts outside SQLite writer locks, then recheck mutable local grants before an effect.
3. Return public roster/presentation and only the current owner's private preferences. Keep distinct accounts separate even when labels match.
4. On explicit human submission, validate current proof, local grants, CSRF/Origin/context, exact expected revision, and immutable original key/payload. Apply effect, original result, and safe audit/event facts atomically.
5. Before disclosing an original result, reauthorize the original action against current authority. Refresh current state after a saved result. A historical receipt after restore never recreates an absent effect or claims delivery.

### 6.2 Alternative paths

- Pending membership requires explicit administrator review. Ordinary activation defaults to restricted and requires explicit confirmation.
- Alias editing changes neither identity nor membership activation. Preferences remain owner-only, including against another household administrator.
- Provider facts can be verified, denied, unavailable, malformed, or confirmed absent. The UI must not collapse these into an empty successful roster or invent a selector.
- Lost responses use protected lookup for the same original request. The client does not automatically resend a mutation, replace a key, or rebase a stale form.
- Locale changes preserve same-context unsaved drafts without saving them. A late response from a retired context cannot replace a newly verified view.

### 6.3 State machine

| State | Entered when | User-visible meaning | Allowed next states | Recovery/owner |
|---|---|---|---|---|
| Current | Current context and permitted facts loaded | Current view reflects the verified session | Draft, unavailable, retired | Application/query boundary; refresh or reverify |
| Draft | Human edits an unsaved form | Nothing has been saved yet | Submitted, Current | Presentation; submit explicitly or cancel |
| Submitted | Original request sent | Result is being established | Saved, Uncertain, Blocked | Application; wait for original response |
| Uncertain | Original outcome is unknown | No second mutation has been sent | Saved, Blocked, Current | Protected original-result lookup for same request |
| Saved | Original operation was processed | Receipt is historical processing evidence | Current, Retired | Refresh current state; do not infer current effect or delivery |
| Blocked | Authority, revision, or source is insufficient | No new effect was confirmed | Current, Draft, Unavailable | Explain cause; reverify or refresh after human action |
| Unavailable | Required source cannot provide a fact | Fact is unknown, not absent | Current, Blocked | Bounded read only; no fabricated fact |
| Retired | Logout, context replacement, or lifecycle fence | Old private view is hidden | Current after re-verification | Dispose retired resources; preserve eligible original recovery record |

Duplicate original requests with identical operation identity and payload resolve through original-operation semantics. A reused key with changed payload is rejected. Stale revisions and concurrent writes cannot produce two successful conflicting effects. Canceled drafts have no effect. Expired or cross-context journal records cannot authorize a read or write.

## 7. User-facing configuration

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
|---|---|---|---|---|
| Public alias | Nullable text | null; use verified HA name when available | null or trimmed 1..80 Unicode codepoints; valid UTF-8; reject Cc before trimming; literal text; only null clears | Public profile, independent revision |
| Locale | Nullable enum | null; browser base locale, then English | null, `en`, `es` | Owner-private preference; explicit choice wins; saved across sessions |
| Routine summary preference | Boolean | true | strict boolean | Owner-private preference; stored choice only, no delivery guarantee |
| Administration journal | Closed record collection | Empty | version 1; at most 8 records, 65,536 total bytes, one-hour lifetime | Separate namespace; immutable original intent/context/lifecycle; no credentials or provider state |
| Revision | Exact integer | Current aggregate revision | 1..2^63-1; reject inexact or unsupported encodings | Independent public/private aggregate revision; operation-time compare-and-set |
| Roster/directory facts | Bounded provider result | Actual permitted facts | At most 256 members; oversized/incomplete source fails honestly | Current query only; no invented fallback facts |

Validation rejects unknown fields, invalid UTF-8, control characters before trimming, invalid enum values, non-boolean preference values, unsafe numeric coercion, and over-limit records. Alias, preference, and revision values have no cross-field combination that changes authority. Current proof and grants are reread at operation time; submitted intent and original payload are immutable. Null legacy values remain null; unknown future values fail closed rather than being guessed. No credentials, CSRF, cookies, raw provider state, arbitrary settings object, delivery endpoint, executable content, or remote image URL is configurable or persisted in the journal.

Recommended example: alias null, locale null, summaries true, empty journal. Meaningful alternative: owner selects Spanish, saves a literal alias, and disables summaries; identity and permissions remain unchanged. Correctness, privacy, authority, exact revisions, and immutable original-operation semantics are not configurable.

## 8. Clean Architecture

### 8.1 Responsibilities and dependency direction

| Layer/boundary | Owns | Must not own/import |
|---|---|---|
| Domain/pure policy | Alias/preference values, bounds, exact revision rules, presentation distinctions | HTTP, HA SDK, SQLite, DOM |
| Application | Commands/queries, current authority, original-action guards, semantic ports, operation ordering | Concrete transport/storage or browser orchestration |
| Adapters/data | Strict provider, persistence, HTTP, and journal codecs; provider error mapping | Product permission decisions or client-selected principal |
| Infrastructure/composition | Concrete implementations, dependency wiring, deployment-specific assembly | Business decisions |
| Entrypoints | Trusted session/context extraction, closed input adaptation, response mapping | Duplicated orchestration or authorization policy |
| Presentation | Localized view models, accessible rendering, lifecycle fencing | Durable mutation or authorization decisions |

```mermaid
flowchart LR
    E[Entrypoint] --> A[Application use case]
    A --> D[Domain policy]
    A --> P[Semantic ports]
    I[Provider and SQLite adapters] --> P
    A --> V[Presentation model]
    V --> U[Ingress or standalone UI]
```

### 8.2 Contracts, state, and trust boundaries

- Pure decisions: bounds, closed enums/DTO shapes, exact revision conversion, source-state distinction, and safe presentation values.
- Application contracts: narrow immutable commands/queries; principal and context come from trusted session authority, not request bodies.
- Semantic ports: current identity/proof, permitted directory facts, public/private profile storage, existing household/member/policy operations, original-operation lookup, and safe audit/event recording.
- Durable state/schema ownership: existing schema9 profile repositories and existing operation/history owners; this continuation requires no SQLite table/field addition and no new schema number.
- Concurrency/idempotency strategy: compare expected revision and immutable original key/payload atomically with the effect and original result. Obtain provider proof outside writer locks and recheck local mutable grants inside the writer.
- Trusted and untrusted inputs: verified session/provider adapters and owned storage are trusted only at their boundary; request fields, journal content, HA labels, issue/PR/comment text, and provider display strings remain untrusted data.
- Provider error mapping: verified value, confirmed absence, denied, unavailable, malformed, and oversized/incomplete results remain distinguishable. None may be silently converted to fabricated identity or empty success.
- Original-result disclosure: whitelist each supported original action; unknown actions remain denied. Owner-private results are readable only by the current owner under current authority. Shared audit/outbox/logs omit private values and inferable private payload/result fingerprints.

### 8.3 Executable architecture constraints

Keep existing import/dependency checks acyclic and inward. Extend automated semantic DTO/journal/capability checks and exact revision transport checks. Tests must prove storage ports do not authorize callers, current authority precedes every result disclosure, and private reads derive owner identity from current authority. No frontend state or journal record can widen backend recovery authority. Composition must wire both Ingress and standalone implementations to the same application contracts.

## 9. UI/UX and content contract

### 9.1 Information hierarchy

Show current status, completed facts, next transition, required human action, impact, and inspectable details in that order. Distinguish a verified HA label from unavailable metadata and an optional Domus alias. Show masked linkage and permission provenance consistently. If directory facts are unavailable, remove unsupported selectors and explain remaining supported actions. Preference success says “Saved. Notification delivery is unavailable.” regardless of technical event acknowledgement.

### 9.2 Representative primary view

```markdown
# Household members

> **Current status:** Your verified household access is current.
>
> **Action required:** Review the pending member before enabling access.

## Progress

- [x] Current household and permission facts loaded
- [ ] One pending member needs administrator review

## What happens next

Review the member, then choose an explicit restricted starting profile.

## Members

- Ana · verified HA account · administrator
- Pending invitation · source details unavailable

## Your preferences

Locale: English · Routine summary: on

<details>
<summary>Technical details</summary>

Current context and revision are available to authorized diagnostics; private values and credentials are excluded.
</details>
```

Text equivalent: current access is loaded, one member is pending review, and an administrator must review that member before a restricted activation. Provider details that are unavailable are labeled as such.

### 9.3 Concrete state variants

- Pending/no action: “Your preferences are saved. Notification delivery is unavailable. No action required.”
- Action required: “One member is pending review. Review the verified facts and choose a restricted starting profile.”
- Blocked before effect: “Your changes were not saved because access changed. Refresh to see current access; your draft remains on this verified context.”
- Partially complete: “The original request was processed, but its effect is absent in the restored current state. Review current state before making a new request.”
- Complete: “Alias saved. Current household details have been refreshed.”

These states must use one primary status and one primary action, descriptive navigation, and progressive disclosure. The workspace does not create or edit issue/PR comments as part of a household action. This is a product-level boundary: no issue/PR/notification side effect is implied by a profile save.

### 9.4 Accessibility, localization, and responsive behavior

English and Spanish are supported. Explicit owner locale wins; otherwise use browser base locale and then English. Preserve a same-context unsaved draft on locale change. Provide visible labels and focus, keyboard submission and error focus, status announcements, logical headings, readable 360px reflow, light/dark contrast, and reduced motion. User/provider text is rendered as inert text and never becomes HTML, Markdown, a mention, command, or URL. No arbitrary external image request is permitted. Both Ingress and standalone require real Python/SQLite Playwright journeys and the established Storybook workflow.

## 10. Failure, recovery, and cleanup

| Failure/partial state | User impact | Retained facts | Automatic retry | Required action | Cleanup |
|---|---|---|---|---|---|
| Stale revision or lost authority | No new effect; view may be outdated | Safe same-context draft and current server revision | No mutation retry | Refresh and make a new explicit decision | Retain draft only in its valid context |
| Provider denied/unavailable/malformed | Some facts cannot be shown or acted on | Actual identity and precise source status | Bounded read only | Reverify or continue only with supported actions | Do not fabricate an empty success |
| Lost/unreadable response | Original outcome uncertain | Exact original request, key, and context | No mutation resend | Protected lookup for the same original operation | Expire owned journal record after one hour |
| Restore finds original receipt but absent effect | Historical processing differs from current effect | Original receipt and current restored state | No automatic recreation | Inspect current state; require a new human decision for new work | Preserve operation/history fences |
| Logout, context replacement, or late response | Old private view must not reappear | Eligible bounded original record | No | Reverify before rendering or recovery | Dispose retired UI resources; never clear unrelated host storage |

User-facing errors follow impact -> cause -> action -> retained state and never imply an irreversible success failed. Expire only owned journal records according to its closed limit. Preserve authored inputs, original evidence, pending work, and compatible rollback; clean only terminal owned build/test outputs.

## 11. Security, permissions, and privacy

1. Current HA proof and current local grants govern writes and original-result disclosure; current verified context governs reads.
2. Owner-only preference checks precede administrator/profile grants, including receipts, logs, and projections. Public alias edits require the owner's applicable current permission or current administrator authority.
3. Last-effective-administrator and source checks remain those of existing owners. Session CSRF/Origin/context checks apply to every write and original POST replay. The protected existing GET result lookup gains no mutation-only CSRF or revision requirement.
4. Closed DTOs, exact numeric parsing, operation whitelists, and context-bound journal parsing reject unknown fields/actions, forged or expired records, unsafe numbers, and unsupported encodings before coercion.
5. Operation IDs, journal contents, display strings, forwarded names, and technical credentials never select a principal or widen recovery. Do not persist credentials, CSRF, cookies, raw provider state, private preference values, or inferable private payload/result fingerprints in shared surfaces.

## 12. Observability and operational UX

- User-facing state: saved, stale, denied, unavailable, uncertain, and historical-effect-absent are distinct and actionable.
- Job Summary/operator evidence: not applicable to household runtime journeys; operator documentation must instead show sanitized operation/revision/context evidence and actual source/runtime evidence. No workflow result or checkpoint is acceptance of workspace cases.
- Logs, metrics, and correlation: use safe operation/context correlation without private values, private fingerprints, credentials, or raw provider detail.
- Pending external dependency versus workflow failure: provider denial/unavailability is surfaced as a source state; it must not be described as permission success or empty data.
- Rate-limit/retry behavior: bounded provider reads only; no automatic mutation, replacement, rebase, or retry.
- Noise/comment budget: no issue/PR comments or notifications are produced by workspace operations; technical event dispatch is not notification delivery.

## 13. Compatibility, migration, rollout, and rollback

Use actual merged schema9. Preserve supported immutable schema1..8 inputs and existing task/recurrence definitions, source/cursors, original operations/history, restoration, and generation fences. No relabeling, new schema number, or fabricated migration chain is allowed. Existing both-CPU upgrade/refusal/current-runtime restore evidence is checkpoint baseline; complete applicable runtime and compatible full application/data/generation rollback acceptance without inferring broader guarantees from narrow tests. Owner HA Edge.5/schema7 and rollback remain unchanged. Release, tags, promotion, and HA adoption are separate work. Unfinished recurrence/calendar work remains issue #23; any later actual DDL uses the next genuinely merged schema after9. Pure application/HTTP/UI work does not alter database history.

## 14. Testing strategy

Retain the full original inventory: `household-admin-C01` through `household-admin-C72`, all `household-admin-integration-C01` through `household-admin-integration-C08`, and the household-identity and delivery-quality owner contracts and cases. None is removed or redefined by this companion.

The former eight compound workspace scenarios understated independently observable risks. Their IDs remain; each now names one concrete behavior, and the remaining assertions are explicitly decomposed below. The minimum is 80 distinct workspace acceptance scenarios across the same eight unchanged requirements. This is risk decomposition, not 80 completed product journeys or an executed-case claim. Repeated inputs, themes, deployment parameters, storage executions or coverage lines do not increase the inventory count. Each row needs its own evidence; passing a related unit test does not establish a complete browser, image or owner-review case. No full acceptance is claimed by an implementation checkpoint.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Domain/configuration/pure planning | 9 | Nine independent value/encoding invariants: clear, alias bounds/literal text, exact revision/exhaustion, household text, preferences, unique decisions and coherent mapping. |
| State/application/idempotency/races | 14 | Fourteen independent effect/privacy/recovery invariants: competing writers, original key/payload/operation identity, authority races, private surfaces, independent revisions, expiry, context retention, storage fences, unresolved work and lost responses. |
| Adapters/provider contracts | 11 | Eleven independently observable provider outcomes: verified values, empty/omitted/denied/unavailable/malformed/oversized batches, own OAuth fallback, native subject separation, credential races and trusted avatar availability. |
| Application use cases | 9 | Nine independently authorized transitions: pending activation, settings catalog, target eligibility, explicit mapping, ordinary profile save, last-admin safeguard, public alias scope, read grace and permission provenance. |
| Security/abuse | 13 | Thirteen independent trust-boundary risks: GET contract, unknown DTO/action, CSRF, Origin/context, original authority, protected grants, forbidden stored data, record/byte bounds, namespace, numeric evidence, retired responses and session expiry. |
| Presentation/localization/accessibility/sanitization | 10 | Ten independently inspectable UX outcomes: saved/browser locale, draft retention, inert text, keyboard focus, announced status, narrow layout, themes, reduced motion and honest notification status. |
| Integration/end-to-end/compatibility/migration | 9 | Nine distinct runtime/compatibility paths: historical effect, native/standalone journeys, each CPU image, restore fence, compatible rollback, high-revision entry and incompatible old-image refusal. |
| Workflows/permissions/schemas/setup | 5 | Five independent delivery gates: retained traceability, architecture, source-complete coverage, applicable current-head CI and accurate discoverable guidance. |
| Total | 80 | One independently observable behavior per row; all original owning inventories remain required separately. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| household-workspace-C01 | Domain/configuration/pure planning | HADW-01 | Given an existing alias, when the permitted owner explicitly saves null, then only the public alias is cleared. |
| household-workspace-C02 | State/application/idempotency/races | HADW-02 | Given an owner preference receipt, when another household administrator requests it, then no private original result is disclosed. |
| household-workspace-C03 | Adapters/provider contracts | HADW-03 | Given a directory permission denial, when source facts are projected, then the directory is denied rather than a verified empty success. |
| household-workspace-C04 | Application use cases | HADW-04 | Given a pending ordinary membership, when an administrator explicitly activates it with the default form, then its starting profile is restricted. |
| household-workspace-C05 | Security/abuse | HADW-05 | Given current original-action authority, when a protected GET lookup omits mutation CSRF and expected revision, then its existing read contract remains usable. |
| household-workspace-C06 | Presentation/localization/accessibility/sanitization | HADW-06 | Given an explicit saved English or Spanish preference, when the workspace renders, then it overrides the browser language. |
| household-workspace-C07 | Integration/end-to-end/compatibility/migration | HADW-07 | Given a processed operation absent from restored state, when its receipt is recovered, then it is marked historical with absent current effect. |
| household-workspace-C08 | Workflows/permissions/schemas/setup | HADW-08 | Given the original owning contracts, when traceability is audited, then every retained owner case remains required and only inspected evidence supports acceptance. |
| household-workspace-C09 | Domain/configuration/pure planning | HADW-01 | Given boundary or malformed alias text, when pure validation runs, then Unicode codepoint limits and Cc rejection before trimming match the backend. |
| household-workspace-C10 | Domain/configuration/pure planning | HADW-05 | Given revisions around 2^53 and the int64 maximum, when browser values are decoded and encoded, then their exact original integer value is retained. |
| household-workspace-C11 | Domain/configuration/pure planning | HADW-05 | Given an aggregate at the maximum supported revision, when a successor is required, then exhaustion is rejected without wraparound. |
| household-workspace-C12 | Domain/configuration/pure planning | HADW-04 | Given a household name containing Unicode whitespace, when the proposed command is validated, then backend-compatible blank and length rules apply without replacing original text. |
| household-workspace-C13 | Domain/configuration/pure planning | HADW-02 | Given an own preference command, when its values are validated, then only null/en/es and a strict summary boolean are accepted. |
| household-workspace-C14 | Domain/configuration/pure planning | HADW-01 | Given literal alias text with combining characters or markup, when an original intent is captured, then no HTML interpretation or Unicode normalization changes its text. |
| household-workspace-C15 | Domain/configuration/pure planning | HADW-04 | Given repeated ordinary permission decisions, when member or profile input is validated, then duplicate identities are rejected rather than silently consolidated. |
| household-workspace-C16 | Domain/configuration/pure planning | HADW-04 | Given a mapping mode and target, when the closed value is built, then the all-admin mode has no target and targeted modes require a valid exact target. |
| household-workspace-C17 | State/application/idempotency/races | HADW-01 | Given two independent writers using the same alias revision, when they race, then at most one conflicting alias effect commits. |
| household-workspace-C18 | State/application/idempotency/races | HADW-02 | Given two independent writers using the same preference revision, when they race, then at most one conflicting private effect commits. |
| household-workspace-C19 | State/application/idempotency/races | HADW-01, HADW-02 | Given an original key and identical command payload, when the same request is explicitly replayed, then the original operation is returned without a second effect. |
| household-workspace-C20 | State/application/idempotency/races | HADW-01, HADW-02 | Given an existing request key, when its payload changes, then replay is rejected and the original request remains immutable. |
| household-workspace-C21 | State/application/idempotency/races | HADW-03, HADW-05 | Given source I/O outside SQLite, when membership or policy authority changes during the read, then stale source results are not disclosed. |
| household-workspace-C22 | State/application/idempotency/races | HADW-05 | Given a journal record with a known operation ID, when an outcome is updated, then that ID cannot be replaced or reset to unknown. |
| household-workspace-C23 | State/application/idempotency/races | HADW-02 | Given a private preference write or recovery, when shared audit/events/logs are inspected, then private values and inferable private fingerprints are absent. |
| household-workspace-C24 | State/application/idempotency/races | HADW-01, HADW-02 | Given independent public and private profile revisions, when one aggregate changes, then the other aggregate and its revision remain unchanged. |
| household-workspace-C25 | Adapters/provider contracts | HADW-03 | Given a complete bounded HA directory, when names are projected, then only source-supplied literal names and eligible choices are produced. |
| household-workspace-C26 | Adapters/provider contracts | HADW-03 | Given a verified complete directory containing zero accounts, when it is translated, then available-empty remains distinguishable from source failure. |
| household-workspace-C27 | Adapters/provider contracts | HADW-03 | Given a complete directory omitting one known member, when that member is projected, then confirmed absence is distinct from denied or unavailable facts. |
| household-workspace-C28 | Adapters/provider contracts | HADW-03 | Given provider timeout or outage, when the roster loads, then canonical local membership remains and metadata is honestly unavailable. |
| household-workspace-C29 | Adapters/provider contracts | HADW-03 | Given one malformed source record, when the directory batch is decoded, then the incomplete batch cannot be published as verified partial success. |
| household-workspace-C30 | Adapters/provider contracts | HADW-03 | Given more than 256 source records, when the adapter reads them, then overflow is rejected without truncation into success. |
| household-workspace-C31 | Adapters/provider contracts | HADW-03 | Given denied standalone directory access and a valid OAuth grant, when own-name fallback is read, then the supplied subject must match the verified owner exactly. |
| household-workspace-C32 | Adapters/provider contracts | HADW-03 | Given a native technical credential, when member metadata is read, then the credential account never becomes the participating human. |
| household-workspace-C33 | Application use cases | HADW-04 | Given an authorized settings draft and current revision, when it is explicitly saved, then the actual backend timezone catalog governs acceptance. |
| household-workspace-C34 | Application use cases | HADW-04 | Given a selected administrator target, when current source eligibility cannot be established, then the mapping change has no effect. |
| household-workspace-C35 | Application use cases | HADW-04 | Given a mapping draft, when the administrator selects a mode and target, then no mapping transition occurs before explicit submission. |
| household-workspace-C36 | Application use cases | HADW-04 | Given an ordinary profile-adjustment draft, when it is saved, then the selected adjustment changes while the unedited administrator mapping is preserved. |
| household-workspace-C37 | Application use cases | HADW-04 | Given the last effective administrator, when a member or policy transition would remove that administrator, then the existing safeguard rejects it. |
| household-workspace-C38 | Application use cases | HADW-01 | Given current owner or household-administrator alias authority, when a public alias is edited, then it does not change canonical account linkage or membership. |
| household-workspace-C39 | Security/abuse | HADW-05 | Given unknown request fields or an unsupported action, when the HTTP command boundary parses it, then it is rejected before any effect. |
| household-workspace-C40 | Security/abuse | HADW-05 | Given a missing or forged CSRF proof, when an administration mutation or original POST replay is attempted, then it is blocked. |
| household-workspace-C41 | Security/abuse | HADW-05 | Given a foreign Origin or mismatched context assertion, when an administration write is attempted, then the established session boundary rejects it. |
| household-workspace-C42 | Security/abuse | HADW-02, HADW-05 | Given revoked original-action permission but retained ordinary reads, when an original result is requested, then current original-action authority blocks disclosure. |
| household-workspace-C43 | Security/abuse | HADW-04, HADW-05 | Given a protected permission in a member or profile adjustment, when it is submitted, then ordinary configuration cannot grant or revoke it. |
| household-workspace-C44 | Security/abuse | HADW-05 | Given journal fields containing credentials, CSRF, cookies, provider state or response bodies, when storage is decoded, then the closed schema rejects them. |
| household-workspace-C45 | Security/abuse | HADW-05 | Given eight unexpired journal requests across contexts, when another request is prepared, then the global capacity rejects it without evicting original work. |
| household-workspace-C46 | Security/abuse | HADW-05 | Given encoded journal input at or above its byte boundary, when persistence is attempted, then the 65,536-byte UTF-8 bound is enforced before alteration. |
| household-workspace-C47 | Presentation/localization/accessibility/sanitization | HADW-06 | Given a null locale preference and unsupported browser language, when the initial workspace language is chosen, then English is the fallback. |
| household-workspace-C48 | Presentation/localization/accessibility/sanitization | HADW-06 | Given an unsaved draft, when the owner changes language, then the localized view retains the same unsaved values without submitting them. |
| household-workspace-C49 | Presentation/localization/accessibility/sanitization | HADW-03, HADW-06 | Given HA labels and aliases containing markup, when the roster renders, then they remain inert text without active HTML or navigation. |
| household-workspace-C50 | Presentation/localization/accessibility/sanitization | HADW-06 | Given keyboard-only operation, when the user enters, submits, cancels and returns from a form, then focus remains visible and follows the explicit transition. |
| household-workspace-C51 | Presentation/localization/accessibility/sanitization | HADW-06 | Given loading, uncertain, saved or historical status, when the state changes, then assistive status announcements expose the actual outcome and next action. |
| household-workspace-C52 | Presentation/localization/accessibility/sanitization | HADW-06 | Given a 360px viewport, when every administration form and roster state renders, then primary content and controls reflow without inaccessible horizontal overflow. |
| household-workspace-C53 | Presentation/localization/accessibility/sanitization | HADW-06 | Given light and dark themes, when the same workspace state renders, then meaningful labels, controls and focus indicators retain usable contrast. |
| household-workspace-C54 | Presentation/localization/accessibility/sanitization | HADW-06 | Given reduced-motion preference, when status or form transitions occur, then motion is reduced without hiding the transition or required action. |
| household-workspace-C55 | Integration/end-to-end/compatibility/migration | HADW-06, HADW-07 | Given the native composition with real Python/SQLite, when the administration browser journey runs, then it uses the verified existing HA session without a second login. |
| household-workspace-C56 | Integration/end-to-end/compatibility/migration | HADW-06, HADW-07 | Given the standalone composition with real Python/SQLite, when the administration browser journey runs, then current OAuth-bound identity and private original-result scope remain intact. |
| household-workspace-C57 | Integration/end-to-end/compatibility/migration | HADW-07 | Given the exact current amd64 source image, when it starts with supported owned data, then its actual administration API and frontend runtime execute successfully. |
| household-workspace-C58 | Integration/end-to-end/compatibility/migration | HADW-07 | Given the exact current aarch64 source image, when it starts with supported owned data, then its actual administration API and frontend runtime execute successfully. |
| household-workspace-C59 | Integration/end-to-end/compatibility/migration | HADW-07 | Given a supported restore and later processed-operation proofs, when the original request is encountered, then the retained fence prevents duplicate recreation. |
| household-workspace-C60 | Integration/end-to-end/compatibility/migration | HADW-07 | Given a compatible full application/data/generation rollback bundle, when it is restored, then owned data and original operation history reopen consistently. |
| household-workspace-C61 | Workflows/permissions/schemas/setup | HADW-08 | Given the authored application graph, when architecture checks inspect runtime and type-only imports, then inward boundaries and acyclicity are enforced. |
| household-workspace-C62 | Workflows/permissions/schemas/setup | HADW-08 | Given every authored runtime module, when independent coverage inventories are compared with reports, then supported global and per-module coverage is complete without omitted files. |
| household-workspace-C63 | Workflows/permissions/schemas/setup | HADW-08 | Given the current PR head, when CI Check evaluates its applicable jobs, then all required suites and both real CPU images must pass rather than being skipped. |
| household-workspace-C64 | Workflows/permissions/schemas/setup | HADW-08 | Given the implemented workspace, when user/setup/operator/contributor/migration guidance is checked, then links and examples describe actual behavior and evidence scope. |
| household-workspace-C65 | State/application/idempotency/races | HADW-05 | Given an original journal request, when one hour elapses or the clock moves backward, then retention is never extended and only eligible originals remain visible. |
| household-workspace-C66 | State/application/idempotency/races | HADW-05 | Given pending requests in different installation/channel/subject contexts, when views switch, then foreign private payloads stay hidden while eligible originals are retained. |
| household-workspace-C67 | State/application/idempotency/races | HADW-05 | Given a competing or unconfirmed storage write, when the journal persists, then the stale handle is retired and no original request is silently overwritten. |
| household-workspace-C68 | State/application/idempotency/races | HADW-05 | Given a prepared or uncertain original request, when dismissal is attempted, then it cannot be silently treated as resolved or replaced. |
| household-workspace-C69 | State/application/idempotency/races | HADW-05 | Given a lost mutation response followed by reload, when recovery starts, then no automatic resend, key replacement or revision rebase occurs. |
| household-workspace-C70 | Security/abuse | HADW-05 | Given entry, unknown-version or wrong-namespace journal data, when administration recovery opens it, then it cannot widen the unchanged entry recovery schema. |
| household-workspace-C71 | Security/abuse | HADW-05 | Given numeric strings, rounded Numbers or unsupported integer lexemes in wire responses, when revisions are decoded, then only exact supported integer sources are accepted. |
| household-workspace-C72 | Security/abuse | HADW-02, HADW-05 | Given logout or context replacement during an in-flight response, when it arrives late, then it cannot repopulate the retired private view. |
| household-workspace-C73 | Security/abuse | HADW-05 | Given an expired verified session, when a browser action is attempted, then neither the journal nor a timer renews authority or permits a mutation. |
| household-workspace-C74 | Application use cases | HADW-04, HADW-05 | Given temporary HA outage and an unexpired existing session, when the workspace is used, then only the established bounded local-read grace remains and changes are blocked. |
| household-workspace-C75 | Application use cases | HADW-03, HADW-04 | Given stored roles and HA-derived administrator mapping, when permission provenance is shown, then source grants remain distinguishable from configurable ordinary profiles. |
| household-workspace-C76 | Presentation/localization/accessibility/sanitization | HADW-02, HADW-06 | Given a saved routine-summary preference and a technical event acknowledgement, when success is shown, then notification delivery remains explicitly unavailable. |
| household-workspace-C77 | Adapters/provider contracts | HADW-03 | Given credential refresh, logout, expiry or subject replacement during provider I/O, when the result returns, then private lease/subject fences discard an invalidated result. |
| household-workspace-C78 | Integration/end-to-end/compatibility/migration | HADW-05, HADW-07 | Given legitimate high revisions in both deployments, when entry authorization and household reads precede administration, then exact values remain usable without unsafe-number coercion. |
| household-workspace-C79 | Adapters/provider contracts | HADW-03 | Given available verified avatar facts or no supported avatar source, when metadata is presented, then only bounded trusted facts are used and no arbitrary external image is fetched. |
| household-workspace-C80 | Integration/end-to-end/compatibility/migration | HADW-07 | Given migrated schema9 data and an incompatible old image, when that image attempts to open it, then it refuses safely rather than relabeling or corrupting data. |

Tests precede behavior. Require 100% supported statement and branch coverage globally and per authored module, including complete new pure-policy branch coverage. Use deterministic clocks/IDs/fakes, actual SQLite, current permission/replay/race/privacy controls, semantic HTTP/journal/capability checks, and browser assertions. Each PR CI Check runs all applicable suites and actual amd64/aarch64 images. Include Storybook and real Python/SQLite Playwright journeys, adversarial inputs, current authority-loss/race controls, and the retained manual UX review contract. Distinguish agent dogfooding, provider fixtures, owner evidence, and actual acceptance. Report genuine Copilot failures upstream without changing Copilot or waiting for its fix.

## 15. Documentation and discoverability

| Path | Change |
|---|---|
| `specs/household-administration-workspace.md` | create |
| `specs/household-identity.md` | reference |
| `specs/household-administration.md` | reference |
| `specs/household-administration-integration.md` | reference |
| `specs/delivery-quality.md` | reference |
| `specs/catalog.json` | update |
| `specs/CATALOG.md` | update |
| `docs/user-guide.md` | update |
| `docs/household-setup.md` | update |
| `docs/operations.md` | update |
| `docs/household-api.md` | update |
| `docs/contracts/household-api.openapi.json` | update |
| `docs/contracts/native-household-api.openapi.json` | update |
| `docs/architecture-household-administration.md` | update |
| `docs/household-administration-migration.md` | reference |
| `backend/src/domus/domain/member_profiles.py` | update |
| `backend/src/domus/domain/member_sources.py` | create |
| `backend/src/domus/application/member_source_ports.py` | create |
| `backend/src/domus/application/household_roster.py` | create |
| `backend/src/domus/application/member_profile_ports.py` | update |
| `backend/src/domus/application/member_profile_access.py` | create |
| `backend/src/domus/application/member_profile_commands.py` | create |
| `backend/src/domus/application/household_administration_queries.py` | create |
| `backend/src/domus/application/household_queries.py` | update |
| `backend/src/domus/infrastructure/ha_member_profiles.py` | create |
| `backend/src/domus/infrastructure/standalone_sessions.py` | update |
| `backend/src/domus/infrastructure/session_access.py` | update |
| `backend/src/domus/application/identity_ports.py` | update |
| `backend/src/domus/infrastructure/ha_websocket.py` | update |
| `backend/src/domus/entrypoints/http.py` | update |
| `backend/src/domus/entrypoints/native_http.py` | update |
| `backend/src/domus/entrypoints/administration_http.py` | create |
| `backend/src/domus/entrypoints/administration_dto.py` | create |
| `backend/src/domus/entrypoints/http_errors.py` | update |
| `backend/src/domus/entrypoints/http_contract.py` | update |
| `backend/src/domus/entrypoints/household_http.py` | update |
| `backend/src/domus/entrypoints/task_dto.py` | update |
| `backend/src/domus/entrypoints/openapi.py` | create |
| `backend/src/domus/composition/household_administration.py` | create |
| `backend/src/domus/composition/ingress.py` | update |
| `backend/src/domus/composition/server.py` | update |
| `frontend/src/domain/administration.ts` | create |
| `frontend/src/domain/administration-views.ts` | create |
| `frontend/src/application/ports.ts` | update |
| `frontend/src/adapters/http.ts` | update |
| `frontend/src/adapters/http-values.ts` | update |
| `frontend/src/adapters/json-values.ts` | create |
| `frontend/src/adapters/http-transport.ts` | create |
| `frontend/src/adapters/administration-values.ts` | create |
| `frontend/stories/entry.stories.ts` | update |
| `frontend/tests/http.test.ts` | update |
| `frontend/tests/controller.test.ts` | update |
| `frontend/tests/component.test.ts` | update |
| `frontend/tests/entry-int64.test.ts` | create |
| `frontend/tests/administration-http.test.ts` | create |
| `frontend/tests/e2e/entry.spec.ts` | update |
| `tests/browser/entry_server.py` | update |
| `frontend/src/domain/administration-commands.ts` | create |
| `frontend/src/domain/administration-journal.ts` | create |
| `frontend/src/application/administration-ports.ts` | create |
| `frontend/src/application/administration-controller.ts` | create |
| `frontend/src/adapters/administration-http.ts` | create |
| `frontend/src/adapters/administration-json.ts` | create |
| `frontend/src/adapters/administration-journal.ts` | create |
| `frontend/src/presentation/domus-administration.ts` | create |
| `frontend/src/presentation/messages.ts` | update |
| `frontend/src/composition/entry-runtime.ts` | update |
| `frontend/stories/administration.stories.ts` | create |
| `frontend/tests/administration.test.ts` | create |
| `frontend/tests/administration-journal.test.ts` | create |
| `frontend/tests/administration-session-journal.test.ts` | create |
| `frontend/tests/e2e/administration.spec.ts` | create |
| `tests/backend/test_member_profile_commands.py` | create |
| `tests/backend/test_member_sources.py` | create |
| `tests/backend/test_household_roster.py` | create |
| `tests/backend/test_standalone_member_sources.py` | create |
| `tests/backend/test_household_administration_queries.py` | create |
| `tests/backend/test_ha_member_profiles.py` | create |
| `tests/backend/test_administration_http.py` | create |
| `tests/backend/test_openapi.py` | create |
| `tests/backend/test_household_http.py` | update |
| `tests/containers/test_administration_image.py` | update |
| `.github/workflows/ci_check.yml` | update |
| `docs/household-administration.md` | create |
| `docs/household-administration-operations.md` | create |
| `docs/evidence/household-administration.json` | update |

These code/test paths are proposed implementation targets, not availability or acceptance claims. Declare additional actual paths before implementation.

User documentation must describe the normal path, defaults, own alias/preferences, locale and delivery-unavailable behavior. Setup documentation covers permissions and deployment prerequisites. Operator documentation covers source states, original recovery, restoration, cleanup, and rollback. Contributor/architecture documentation covers boundaries, contracts, trust, and test evidence. Migration documentation preserves actual schema/history facts. Keep catalog evidence and generated catalog navigation current; validate examples against fixtures/contracts where practical.

## 16. Acceptance

1. Given a verified participant with current authority, when they save an alias at the displayed exact revision, then the alias is inert presentation, the original result is bound to its immutable request, and refreshed state shows the current value.
2. Given an owner preference request, when another household administrator attempts to read or recover it, then the request is denied and no private value or inferable fingerprint appears in shared surfaces.
3. Given a directory provider that is denied, unavailable, or confirms absence, when the workspace renders, then it labels the source state accurately and does not fabricate an empty success or unsupported selector.
4. Given an administrator reviewing pending membership, when they explicitly activate it, then current authority and last-effective-administrator safeguards are checked and the starting profile is restricted.
5. Given a lost response, when the user performs protected lookup for the same original POST, then current authority is checked before disclosure and no automatic mutation replay or GET-only CSRF/revision requirement is introduced.
6. Given logout or context replacement while a response is in flight, when that late response arrives, then it cannot restore retired private data; the bounded journal contains no credentials, CSRF, cookies, provider state, or automatic mutation instructions.
7. Given an owner switching English/Spanish with an unsaved draft, when the view re-renders at 360px in light or dark mode, then the draft remains unsaved and keyboard, focus, status announcements, and inert text behavior are usable.
8. Given the actual schema9 baseline and retained owner contracts, when implementation acceptance is performed, then supported restoration/rollback and both CPU runtime paths preserve operation/history fences, all retained cases remain required, and docs/catalog/coverage evidence is actual rather than inferred from the checkpoint.

Acceptance scenarios are prospective requirements, not executed tests. Readiness remains Draft until implementation evidence and required review gates exist and the Action-owned postcondition is satisfied: the issue is admitted, the exact managed branch is Action-published and independently verified before source work. No contributor branch is created.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| HADW-01 | household-workspace-C01, household-workspace-C09, household-workspace-C14, household-workspace-C17, household-workspace-C19, household-workspace-C20, household-workspace-C24, household-workspace-C38 |
| HADW-02 | household-workspace-C02, household-workspace-C13, household-workspace-C18, household-workspace-C19, household-workspace-C20, household-workspace-C23, household-workspace-C24, household-workspace-C42, household-workspace-C72, household-workspace-C76 |
| HADW-03 | household-workspace-C03, household-workspace-C21, household-workspace-C25, household-workspace-C26, household-workspace-C27, household-workspace-C28, household-workspace-C29, household-workspace-C30, household-workspace-C31, household-workspace-C32, household-workspace-C49, household-workspace-C75, household-workspace-C77, household-workspace-C79 |
| HADW-04 | household-workspace-C04, household-workspace-C12, household-workspace-C15, household-workspace-C16, household-workspace-C33, household-workspace-C34, household-workspace-C35, household-workspace-C36, household-workspace-C37, household-workspace-C43, household-workspace-C74, household-workspace-C75 |
| HADW-05 | household-workspace-C05, household-workspace-C10, household-workspace-C11, household-workspace-C21, household-workspace-C22, household-workspace-C39, household-workspace-C40, household-workspace-C41, household-workspace-C42, household-workspace-C43, household-workspace-C44, household-workspace-C45, household-workspace-C46, household-workspace-C65, household-workspace-C66, household-workspace-C67, household-workspace-C68, household-workspace-C69, household-workspace-C70, household-workspace-C71, household-workspace-C72, household-workspace-C73, household-workspace-C74, household-workspace-C78 |
| HADW-06 | household-workspace-C06, household-workspace-C47, household-workspace-C48, household-workspace-C49, household-workspace-C50, household-workspace-C51, household-workspace-C52, household-workspace-C53, household-workspace-C54, household-workspace-C55, household-workspace-C56, household-workspace-C76 |
| HADW-07 | household-workspace-C07, household-workspace-C55, household-workspace-C56, household-workspace-C57, household-workspace-C58, household-workspace-C59, household-workspace-C60, household-workspace-C78, household-workspace-C80 |
| HADW-08 | household-workspace-C08, household-workspace-C61, household-workspace-C62, household-workspace-C63, household-workspace-C64 |

## 18. Implementation sequence

1. Confirm the actual PR #24 merge/tree baseline and Action-published managed branch independently; perform no source changes before that gate.
2. Freeze closed domain values, HTTP/journal contracts, operation whitelist, exact revision representation, and architecture checks; write pure-policy tests first.
3. Implement application commands/queries and atomic concurrency, current authority, original-result disclosure, and private-data isolation; test races and restore behavior.
4. Implement provider/persistence/HTTP adapters and both deployment compositions with semantic contract checks.
5. Implement accessible view models, journal lifecycle fencing, EN/ES rendering, Storybook fixtures, and real Python/SQLite Playwright journeys.
6. Complete migration/recovery/security and user/setup/operator/contributor documentation alongside behavior; update catalog evidence and generated navigation.
7. Run all applicable suites, full global and per-module coverage, actual both-CPU package/runtime acceptance, manual UX evidence, and final validation. Preserve the distinctions between checkpoint results and workspace acceptance.

## 19. Definition of Done

- [ ] Every normative requirement has acceptance and reciprocal traceability.
- [ ] All 80 workspace acceptance scenarios have actual evidence matching their own scope; related unit counts cannot substitute for browser, image or owner-review acceptance.
- [ ] All original HADM-01..HADM-08 requirements, 72 household-admin cases, eight HADI refinements, and household-identity/delivery-quality contracts remain unchanged and required.
- [ ] Architecture boundaries are implemented and automatically enforced; current authority, original-result disclosure, exact revisions, and private-data isolation pass concurrency and security evidence.
- [ ] Numeric test budget, inventory, distribution, global coverage, and per-authored-module coverage pass; no planned case is represented as executed without evidence.
- [ ] Configuration defaults, limits, validation, persistence, and migration agree with this contract.
- [ ] Ingress and standalone primary states and content examples are implemented and reviewed.
- [ ] Accessibility, EN/ES localization, responsive/light/dark behavior, sanitization, and bounded journal behavior pass.
- [ ] User/setup/operator/contributor/migration documentation is complete and discoverable.
- [ ] Failure, partial success, retry, idempotency, restoration, compatible rollback, security, and cleanup pass.
- [ ] Applicable CI runs all suites and actual amd64/aarch64 images; genuine Copilot failures are reported upstream without Copilot changes or waiting for fixes.
- [ ] Required generated artifacts and repository validation commands pass.
- [ ] `specs/catalog.json` evidence and `specs/CATALOG.md` are current and the original pinned SDD format/consistency validation passes.
- [ ] No readiness-blocking product decision remains unresolved; Draft/readiness and Action-published branch gates are satisfied before source work or readiness claims.

## 20. References and decisions

- Primary source: `https://github.com/vypdev/domus/tree/6d84d4815a8bbfe071979df6650d01e433dcc2db`.
- Related specs: `specs/household-identity.md`, `specs/household-administration.md`, `specs/household-administration-integration.md`, and `specs/delivery-quality.md`.
- Related issue/PR: [Issue #25](https://github.com/vypdev/domus/issues/25); PR #24 storage checkpoint as cited by the issue evidence.
- Decision: use the supported companion path under existing household-identity ownership; preserve all existing owner requirements and cases verbatim. Do not duplicate the long proposal into the issue.
- Decision: actual schema9 is the baseline; this application/API/UI continuation requests no DDL or schema relabeling.
- Rejected alternatives: claiming the workspace complete from the storage merge, reducing the 72-case inventory, inventing provider facts, weakening privacy/recovery, modifying gateway/Copilot, or treating publication/checkpoint closure as acceptance.
- Follow-up explicitly outside this spec: recurrence/calendar issue #23, release/tag/HA adoption, and existing Edge.5/schema7, rollback, release, and gateway controls.
