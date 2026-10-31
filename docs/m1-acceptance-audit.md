# Identity, persistence and restoration acceptance audit

Status: review candidate for issue #6 / PR #7, audited on 2026-10-31. This foundation increment
does not complete M1 or the first usable product. The [identity companion](../specs/platform-foundation-identity-sqlite.md)
and [restoration companion](../specs/platform-restoration.md) retain their normative inventories.

The [machine-readable audit](evidence/m1-acceptance-audit.json) maps all 61 identity cases and
18 restoration cases to 171 exact semantic test selectors or explicitly bounded observation
documents. Selectors were resolved against Python AST definitions; an existing name is only a
traceability check. Assertions, real-file/process behavior and the separate compatibility evidence
establish the stated behavior. Case counts are planned acceptance cases, not pytest execution totals.

## Verification and changes

The complete backend run passes **1,387 tests**, with **4,692 statements and 1,304 branches at
100% supported coverage**, including every authored backend module. No coverage omission or custom
exclusion was added. The independent default-permission matrix now checks every role/permission pair.
New composed tests exercise both transports, every membership state, unsupported locale fallback,
safe console diagnostics, original enrollment replay after activation and historical enrollment after
restoration. The tests failed on the missing explanation before the presenter change.

`GET /api/v1/authorization` now supplies English `message` and `action_required` fields explaining
current membership and the next action. Enrollment receipts describe the original operation in the
past tense: pending enrollment verified and linked an account but did not activate access. Replaying
that original operation after activation preserves the receipt; current authorization reports the
new state. Historical receipts still say their effect is absent from current state. No permission,
authentication, persistence or recovery rule changed. Both published OpenAPI contracts reflect the
actual composed servers.

API/console content was inspected by the assistant as plain text with explicit status, impact,
retained state and next action. Unsupported locales retain stable codes and English text; untrusted
diagnostics do not become HTML, Markdown, mentions, commands or URLs. Independent human readability
review remains required. Product UI and mobile browser layout acceptance belong to subsequent work.

## Exact deployment boundaries

The installed Edge.3 package remains pinned to runtime
`faa1654a5c9cddb562bfcd4c02d4cebfeb78e9f5`. These new source explanations are not installed there.
The [real-image evidence](evidence/m1-restoration-app-package.json) proves packaged restore,
interruption/resume, previous-image upgrade and old-image refusal on the identified images. The
[owner acceptance](evidence/m1-edge3-ha-acceptance.json) proves only update, configuration, session,
reload and restart. It does not prove a live household mutation, recovery or restore.

A separate read-only Chrome About observation on 2026-10-31 confirmed Core **2026.10.4**, Supervisor
**2026.10.5**, HA OS **18.3**, Frontend **20260930.5**. No owner data or configuration changed.
The [compatibility matrix](compatibility-home-assistant.md) keeps standalone browser return and
other unexecuted target combinations pending. Earlier immutable receipts retain their original
observations and limits.

## Review gate and subsequent scope

The draft PR's Bugbot check was skipped because draft reviews are disabled; that is not a clean
review. Merge requires all current-head CI groups, full supported coverage and a complete current-head
Bugbot review without unresolved findings. The audit records this as pending rather than claiming
the gate passed. Copilot implementation and installed resources remain untouched.

Issue #6 excludes the product UI, companion HA entity/service integration and complete release/channel
distribution. They remain part of the full product goal and require their own Action-admitted work.
The next interface increment must consume these application contracts, preserve Clean Architecture,
and start with component, browser, accessibility and coverage checks.
