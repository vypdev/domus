# Standalone sign-in recovery

Issue: [#178](https://github.com/vypdev/domus/issues/178).
Existing owners: [household entry](../../specs/household-entry-interface.md) C18, C20 and C45,
and [platform identity](../../specs/platform-foundation-identity-sqlite.md) C43 and C53.

## Defect and behavior

A real standalone sign-in returned after its five-minute attempt had expired. Domus correctly
rejected it, but the browser displayed the API JSON without an actionable localized recovery
interface. Public authentication fixtures reproduce the same missing/expired binding rejection.

An invalid standalone callback now sends a normal HTML navigation to the fixed same-origin
`/#sign-in-recovery` destination. The root interface explains that the previous attempt is no
longer valid and household records are retained. Its existing sign-in control starts a fresh
attempt only after deliberate activation. English keyboard and narrow Spanish touch are owning
acceptance paths. The control receives focus when missing proof is established; a language change
or an equivalent already-ready state does not take focus away again.

HTML must be explicitly acceptable and have a higher quality than the JSON representation.
Explicit JSON, its applicable wildcard, equal preference, absent HTML, zero quality and malformed
quality retain the existing 401 JSON envelope. An explicit JSON media range takes precedence over
its wildcard. Both callback representations retain no-store/no-referrer protections and vary by
Accept. Other authentication, validation, boundary and route failures keep their existing behavior.

The public fragment changes presentation only. Current server proof still determines access.
Native Ingress, loading/closed views and an existing verified session retain their normal state.
Unknown or extended fragments cannot select a destination, provide proof or expose callback data.
The four nonpersonal bootstrap fields, restrictive CSP and fixed navigation capability are retained.

The rejected code is not exchanged. Recovery neither creates/extends a session, renews an attempt,
revokes an unrelated valid session nor replays household work. No callback field is copied into
the redirect or rendered text. The existing state, browser binding, PKCE, single-use, exact-origin
and current-user checks remain in force. No storage schema, dependency or shared package API changes.

## Existing acceptance cases

| Existing owner | Concrete witnesses |
|---|---|
| Entry C18; identity C43/C53 | `test_auth_http.py` covers missing, malformed, wrong and exactly-expired binding; a forbidden exchange sentinel; original JSON and content negotiation; deliberate new bound sign-in; unchanged unrelated session and no revocation. Existing callback/state/PKCE/concurrency tests remain. |
| Entry C20 | `sign-in-recovery.spec.ts` creates a real household, signs out, retires only its disposable browser binding, follows the rejected callback and deliberately completes a fresh fixture sign-in. Current records remain. The same file is included in source and both actual-image inventories. |
| Entry C45 | Backend responses exclude callback code/state; mounted page tests keep the exact fragment non-authoritative and reject extended guidance markers. Verified standalone and native browser journeys request no household writes or sign-in from a public marker. |
| Entry C33–C36 | Component tests cover EN/ES guidance, one explicit action and focus. The new catalog state checks 390 px layout, both themes, contrast, target height and keyboard/touch intent with no connected API. |

Selectors live in [auth HTTP tests](../../tests/backend/test_auth_http.py),
[component tests](../../frontend/tests/component.test.ts),
[page composition tests](../../frontend/tests/page.test.ts),
[product journeys](../../frontend/tests/e2e/sign-in-recovery.spec.ts) and
[catalog journeys](../../frontend/tests/e2e/catalog.spec.ts).
These extend existing owners without introducing or renumbering specification cases.

## Local source checkpoint

The Action created the linked issue branch from accepted develop
`b65c2315ca5e0715ccc3b90f4288b776f842942b` after its CI and Branch Sync passed.

- Eighteen new backend regressions failed on the original behavior; five additional preference
  regressions rejected incorrectly selected HTML before quality ordering was corrected.
- The targeted authentication/review/UI HTTP campaign passes 124 cases. The complete backend
  campaign passes 6,106 tests with every one of the unchanged 250 authored modules at complete
  line/branch coverage. Independent source-inventory and coverage audits pass.
- All 2,306 Chromium unit/component tests pass. All 121 authored TypeScript files are audited,
  including seven empty type files; statements, branches, functions and lines are complete
  globally and per nonempty file.
- Runtime/catalog type checks, Python style and the 250-file type check pass. All 48 CI contract
  cases pass with the strengthened actual-image inventory.
- All 173 composed source browser journeys and 70 rebuilt catalog journeys pass, with zero
  skipped, unexpected or internally retried/flaky results. The four new product journeys
  independently passed before the full inventory. Original reports and EN keyboard/ES 390 px
  touch captures are retained. All 42 Node policy and 51 Python architecture cases pass.
- Discovery finds 118 actual-image journeys, retaining every previous journey. That discovery
  is not image execution evidence; both CPU image suites and installed acceptance remain pending.

The product journey exposed a redundant generic authentication notice beneath the new explanation.
Recovery now consolidates only that duplicate notice. Existing notices retain their ordinary scope;
the complete frontend coverage campaign and composed journeys passed after this correction.

The browser fixture uses missing binding without changing an installed clock. Its backend
companion separately exercises the exact five-minute expiry boundary. Actual owner acceptance
must record its own provider, immutable candidate and natural expired-attempt observations.

## Immutable Edge.95 preparation

- Runtime source: `aa5baf97b938a0450f07d6b13a49f2e696795ca3`.
- Source archive SHA-256: `c1b8fc3961a6a1361b7e8fca8085d1dded5962cff6d47a622a5837f5afbd718b`.
- Wheel SHA-256: `29bd0fb85c3c55eb3e34debaa73dff08fd1778568e12b3749d62eef0bfbf756c`.
- All 1,043 archive files match their Git blobs. An independent frozen build binds all 250
  Python modules and four UI assets to the tested source. Its noneditable installed runtime
  matches the wheel. Only the HTTP entrypoint changed among the 250 Python modules.
- Storage schema remains 37; the exact published ha-ui cohort remains 0.1.0-next.5.

The [artifact declaration](../../addon-edge/artifact.json) and
[bounded qualification record](standalone-sign-in-recovery.json) identify these bytes.
This is package preparation; actual CPU image and installed acceptance are separate gates.

## Remaining gates

Exercise the installed standalone recovery and native behavior. Both CPU image suites and substantive review must pass
on the final head before merge; destination CI, Branch Sync and issue closure follow independently.
Full M1/M5, production HTTPS and Stable distribution acceptance remain separate roadmap work.
