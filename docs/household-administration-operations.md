# Household administration operations

The development workspace supports both native Ingress and standalone deployments. Ingress uses
its verified Home Assistant session; standalone uses the existing Home Assistant sign-in flow.
Each person needs a separate Home Assistant account. A display name or Domus alias never grants access.
The Edge.6 installation candidate pins the reviewed workspace runtime. Publishing its definition does
not update an installed application; actual owner adoption and Stable acceptance remain separate.

## Current access and data

The workspace verifies identity and household access before displaying administration. It hides
private forms while checking access and when a session expires or its participant changes. The
stored profile and the effective profile for the current session are shown separately: HA mapping
can make these different. Technical details show the server's current permission set.

A read-only outage lease permits available local reads and authorized original-result checks until
its existing deadline. It does not permit configuration changes or extend that deadline. A missing
roster does not prevent reading an independently permitted own alias. HA names can be available,
confirmed absent, denied or unavailable; an unavailable name or avatar is never invented.

## Review a change

Choose an available edit, adjust values, select **Review changes**, and inspect the confirmation
before **Save changes**. Participant edits identify the participant and stable membership reference.
Validation messages describe the form controls and return keyboard focus to a relevant field or
required approval. **Back to editing** restores the initial control and retains entered values.
If a transition target is disabled or no longer available, focus moves to the enabled
**Refresh administration** action. During proof refresh or retirement, removed private controls
are not focused.
Household settings, access policy, member configuration, public alias and private preferences each
keep their own original revision. An unrelated edit does not replace that revision.

A pending member starts the editor with a restricted profile. Activating that member requires an
explicit access confirmation. An administrator can adjust ordinary permissions by profile or member;
protected administration permissions cannot be edited. Inherited settings are preserved unless
explicitly changed. The HA mapping editor preserves its stored target when current directory or
membership facts cannot support a new selection. The server verifies eligibility and a remaining
administrator; names alone cannot prove either.

An optional alias changes public presentation only. The default uses an available HA name. Only the
participant can save their private locale and routine-summary preference. Saving summaries currently
sends no notification. A saved English/Spanish locale overrides the browser; an unset locale follows
the browser with English fallback. The header's language choice is temporary and sends no mutation.

A draft retains its original revision through translation, same-participant refresh and a rejected
preflight. **Reset from current data** explicitly adopts fresh values and revision. If the data that
permit viewing a draft become unavailable, its fields and confirmation are hidden until they can be
read again. Losing only write access leaves readable values inspectable and disables saving. A
participant/account/installation/channel or verified household ID change, missing household proof, logout
or component retirement clears private drafts. Matching participant IDs or revisions do not transfer a
draft to another household. A pending refresh without a published view can retain it for fresh matching
proof; a detached confirmation control cannot submit a retired draft.

## An unknown result

The administration journal is separate from entry/setup recovery. It holds at most eight requests
and 65,536 bytes across contexts for one hour. It preserves the original action, payload, key and
revision before sending. Storage does not grant permission to inspect a result.

Use **Check original request** deliberately. It performs a protected original key/operation GET;
it does not resubmit a mutation, silently adopt a newer revision or replace unresolved work. Closing
an editor does not undo a server effect. A resolved record can be hidden locally without deleting
server history. An unresolved record cannot be dismissed to bypass this protection.

A conflict found during preflight can stop before any HTTP mutation or original record exists.
Review its access/data notice and reset explicitly when appropriate. A processed receipt describes
original processing; it does not guarantee that later state still has that effect. After restoring
a snapshot, historical processing can be retained while the original effect is absent. Inspect current
facts before requesting new work. Do not use a historical receipt to repopulate private preferences.

## Leaving and restoring the page

Leaving the page retires its private view and resources. Returning requires current proof before
private facts are shown again; a previous unsent editor is not revived. Private `no-store` responses
can cause Chromium to reload on back navigation. Browser caching eligibility does not grant access.

Restoring a closed tab can retain that tab's original journal. The workspace still verifies current
identity and requires an explicit original-result check. Opening an unrelated new tab does not copy
the old tab's journal. The server retains original processing proof independently; a missing local
record does not prove that its effect never happened.

The navigation checks distinguish normal no-store reloads from actual BFCache in a separate browser
with an explicit cache policy. Product headers remain unchanged. Closed-tab checks use the public
[Chromium sessions API](https://developer.chrome.com/docs/extensions/reference/api/sessions) in a
disposable test profile with a generated test-only extension; they do not modify the owner's Chrome.
The [Chrome no-store policy](https://developer.chrome.com/docs/web-platform/bfcache-ccns) explains why
normal back navigation and conditional persisted navigation need separate assertions.

## Verification and rollout

Run `pnpm test:frontend` for actual Chromium component/controller coverage and its independent source
inventory audit. Run `pnpm build:frontend`, build the backend wheel, and run `pnpm test:frontend-entry`
for the compiled browser with disposable Python/SQLite Ingress and standalone fixtures. These fixtures
use fictional HA accounts and cannot establish owner-HA adoption.

Run `pnpm build:frontend-catalog` and `pnpm test:frontend-catalog` for the built entry and administration
catalog, including English/Spanish, keyboard focus, inert text, narrow layout and both color schemes.
Catalog stories explicitly emit intents without a server. They do not fabricate successful operations.
The **Maximum Labels** administration story contains 256 fictional participants. Every HA name uses
the full 256 Unicode code points (1,024 UTF-8 bytes); alternating rows use an 80-code-point alias
(320 bytes) or the HA-name fallback. At 360px, the built-browser acceptance checks every row's
text/action geometry without clipping, scrolls to the final participant and opens its management
and alias forms. Reordering the roster preserves the selected membership reference and exact
alias draft. Confirmation emits one intent for that same member. Both languages, deployment
presentations, themes and reduced motion are covered. This is compiled presentation evidence;
it does not assert a live HA directory response, successful server write or human UX approval.
All 34 administration journeys also execute against the actual current image on each CI architecture,
including exact high revisions, independent-writer conflicts, original recovery, authority outage,
keyboard errors, closed-tab restoration, conditional BFCache and actual console restoration.
Set `DOMUS_BROWSER_IMAGE` to the reviewed local image, `DOMUS_TEST_SOURCE_COMMIT` to its exact revision,
and `DOMUS_TEST_ARCH` to `amd64` or `aarch64`; run the entry Playwright configuration against the whole
`administration.spec.ts` file without a name filter. Docker must be available to the test process.
The fixture verifies source/image/CPU identity and starts isolated nonroot containers without published
ports or host mounts. Framed stdio workers preserve each original HTTP request, headers and binary body;
workers remain independent across host transport threads and match responses to their original frame.
Each frame makes one inner HTTP request with a fresh connection. I/O failure never resends a mutation.
Provider fixtures are copied only into the disposable writable container; no test dependency is added
to the image. The command must report all 34 passing journeys with no skips or flaky results. CI requires
that exact receipt in both CPU jobs, within the unchanged global suite limit of 180 seconds.
The runner uses a bounded graceful shutdown so the bridge can retire its owned container before
reporting ASGI completion. CI also requires
`docker ps --all --quiet --filter label=domus.browser-fixture=true` to be empty after the campaign;
any remaining disposable fixture fails the job. The outer final cleanup is idempotent.

The container suite also requires `DOMUS_SCHEMA9_IMAGE`, the compatible immutable administration
checkpoint `87d726fa5a6a8cbcb56e0b911d15cc5b8a96a470`. Build it from
`tests/fixtures/schema9-app`; its source archive is verified by SHA-256 before either the original UI
or Python package is built. This is a development compatibility fixture, not an installed HA release.
Both CPU jobs run four application/data/generation rollback scenarios: native and standalone, each
with pending or acknowledged original event evidence. The older application creates a schema9
checkpoint, the current application commits separate public/private updates and activates restoration,
and the older application reopens the selected generation with its original UI. Exact household,
member, policy and profile state returns; original receipt, fingerprint, result, time, audit, event
payload/position and delivery proof survive. Explicit replay returns historical original operations
without changing database bytes or creating effects. No owner data or host directory is mounted.

The owning SDD acceptance audit and required human UX review remain separate gates. Before owner rollout,
verify the exact package, both CPU images and compatible data/rollback procedure. Preserve the installed
owner Edge.5 and Edge.3 rollback until that adoption is verified.

## Pinned Edge.6 installation candidate

The Supervisor recipe in `addon-edge` pins reviewed source
`3200bd9278f57f142ed03b54843a38a4138fc0af` and its exact archive digest. The
[artifact declaration](../addon-edge/artifact.json) records all 151 Python and four compiled UI
fingerprints plus the reviewed source-wheel reference. The installed-image check independently
reads those product files as a nonroot user; an image is not identified by its mutable tag alone.
The version is `0.0.0-edge.6`, with the same private listener/Core permission scope and schema 9.
Read [installation, backup and rollback limits](../addon-edge/DOCS.md) before adoption.

The original Edge.5 Dockerfile remains byte-identical in `tests/fixtures/edge5-app`; it has no
discoverable app configuration and does not become a second Supervisor listing. Build that fixture
as `DOMUS_SCHEMA7_IMAGE`, the actual `addon-edge` candidate as `DOMUS_EDGE_IMAGE`, and the normal
current-source/other compatibility images before running `uv run pytest tests/containers --no-cov`.
Both CPU jobs now require the actual preview's product-file, native restart/authority, standalone
delivery and real Edge.5 upgrade/replay/restoration checks in addition to the existing suite.
The current-source image runs all 34 administration browser journeys per CPU. A prior separate local
aarch64 campaign has also passed all 32 journeys against the actual pinned Edge.6 image.

These isolated campaigns do not change the installed owner's Edge.5 or create a household.
Fresh Chrome observation confirms the current Edge.5 identity and empty setup state; actual update,
owned backup/compatible rollback, live administration and human UX review remain unproven.

The pending-alias journey independently preserves the exact pending membership and canonical source
facts through an administrator alias save. Only a later explicit restricted activation grants access;
the same participant then reads unchanged default private preferences and the saved public alias.
The [HA installation guide](installation-home-assistant.md) distinguishes the actual old branch source,
current candidate and completed owner-only backup from an unperformed update or data migration.
