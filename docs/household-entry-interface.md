# Household entry interface foundation

The development branch implements pure entry/setup decisions, the bounded request journal with
its owned sessionStorage adapter, and the generation-fenced entry controller. The product entry
page, frontend HTTP adapters and static delivery remain to be implemented. Both server compositions
now expose verified session context and enforce supplied context assertions before protected work.
These tests do not add a working interface to the owner's installed Edge.3 application.

The [entry specification](../specs/household-entry-interface.md) retains eight requirements and 48
planned acceptance cases. The first model tests exercise membership decisions, explicit setup
defaults, input bounds and truthful unavailable facts; they do not complete browser journeys.

## Decisions and setup

The model consumes decoded server facts and never infers a grant from a profile name. Setup and
enrollment controls require the server's corresponding flag and a full, unexpired session. Pending
membership offers refresh; suspended or archived membership asks an administrator to review the
existing linkage. Those states never offer replacement self-enrollment.

Read-only grace retains the membership state and disables setup and enrollment. Household facts
are displayable only for active membership with the actual household.read grant. The server checks
each request independently. A model decision never extends the original deadline. Missing, expired
or inconsistent proof selects native HA reopening or the existing standalone sign-in path. Missing
data and preview without household APIs remain unavailable.

Setup takes only name and timezone. It selects all_ha_administrators, expected revision zero, and
no actor or selected account. Names are bounded to 160 Unicode code points before trimming; timezones
to 128. Blank, Unicode-control (C0, DEL and C1) and unpaired-surrogate input receives a field error without changing
the caller's draft. The server owns final authorization, uniqueness and timezone-catalog validation.
These checks do not authenticate or send a command.

## Original requests and local recovery

The version-1 journal holds up to eight requests in at most 64 KiB of canonical UTF-8 JSON. Setup
and own enrollment have exact allowed fields; transport credentials, raw errors and arbitrary actions
are rejected. The original key, payload, creation time and one-hour deadline remain immutable across
reload, uncertain outcomes and committed/historical results. Validation never normalizes a stored
payload. Known operation IDs cannot change or be replaced with an uncertain/rejected outcome.

Fresh server context binds one installation, Stable/Edge channel and verified subject. Opening may
establish an empty owned local journal after current-state reads; this writes no household/member
record. A known different context removes incompatible local requests before use. Invalid/future
versions, malformed or noncanonical JSON, duplicate keys, future timestamps and clock regression
block use. Updating the observation time never extends an original deadline. Expired records may
be pruned; unresolved unexpired work is never silently evicted. Resolved requests can be dismissed.

The adapter touches only domus.entry.journal.v1. Every update compares the prior serialized value,
writes and confirms readback. Failure, external change or disappearance invalidates the opened
handle. A controller must obtain fresh server context/state before reopening and must persist a
prepared request before any send. The journal cannot grant access or prove current membership.

Involuntary session loss detaches memory and retains local recovery evidence. Explicit logout clears
memory first and removes/verifies only the owned key. Failed cleanup is reported as uncertain; it
never restores authority. A storage failure after receiving a server receipt does not negate that
receipt or justify a new request key. Adapter tests use simulated receipts plus actual isolated
Chromium sessionStorage, without contacting the owner's HA.

## Entry controller

Opening and refreshing read session, current authorization and permitted household facts. They
create no household or membership. Semantic server ports must bind each read and command to the
expected installation/channel/subject, reject a mismatch, and return strictly decoded immutable
facts. Expected context is an assertion, never an actor selector. Both server compositions now reject
supplied mismatched assertions; the frontend HTTP adapter must still attach and validate that contract.
Domain and Application import no browser, storage, transport or framework API.

Setup, enrollment, original-request recovery and resolved-request dismissal obtain fresh session
and current state. Setup uses the explicit validated default mapping. Recovery is separate from
eligibility for a new effect: pending enrollment may check its original request; setup recovery
requires current setup permission or an active household-management grant. The server independently
enforces current original-command authority and idempotency. Rejection, missing proof, grace,
suspended/archived linkage and incompatible context never become a cached grant.

One command is allowed in flight, including its preflight and receipt reconciliation. A new key is
not generated while unexpired prepared/uncertain work exists. Prepare must persist and read back
before send. No opening, refresh, receipt, timeout or transport failure automatically resubmits.
Deliberate recovery reuses the exact original key/payload, creation/deadline and known operation
identity; changes observed during fresh reads fail closed. Dismissal cannot evict unresolved work.

Every replacement view cancels owned reads and fences all late results, including rejected reads,
sent responses and logout callbacks. Cancellation never claims to undo a command. Involuntary loss
or teardown detaches memory and preserves local recovery evidence. Tick uses the semantic anchored
clock; it never renews a session. Tick hides expired recovery records and completed results; a fresh
verified opening prunes expired stored records. A receipt arriving after session expiry remains
evidence of the earlier effect but cannot expose expired authority. Explicit standalone logout attempts actual logout even
if owned storage clearing fails. Native logout clears owned presentation/data and explains that HA
owns sign-out; it never invokes standalone revocation. Cleanup/revocation uncertainty stays explicit.

The controller tests use real Chromium and semantic server fakes, including one processed effect
whose first response is lost and then recovered after controller/storage-adapter recreation. These
are Application tests, not real HTTP/SQLite, rendered journeys, owner HA or package acceptance.

## Server context contract

The actual authenticated session response contains context with installation_id, channel,
deployment, application_base, household_api_available, server_time and expires_at. Native derives
the base from the accepted Supervisor prefix; standalone always uses the root. Forwarded prefixes
cannot replace either. UTC epoch milliseconds are anchored once to the monotonic lease clock;
later wall-clock changes and fresh/grace reads cannot extend the original session deadline.

Bound UI requests must supply X-Domus-Context as v1:installation:channel:subject, using verified
metadata and the verified HA user ID. The server compares this assertion with its real composition
and session before protected reads/CSRF/commands. Wrong or ambiguous assertions receive a safe
rejection without revealing expected context or creating a household. The assertion grants no role
and selects no actor. Legacy raw API requests may omit it; the upcoming frontend adapter must always
send it on bound requests. Existing cookie/Ingress, Origin, CSRF and per-command current authority
remain mandatory. No CORS permission or public port is added.

Thirty-three additional backend scenarios exercise actual guarded ASGI/SQLite and both compositions,
including metadata, preview, stale context, role denial, original-key replay and fixed clock anchor.
These server tests do not wire the frontend adapter or prove rendered/owner acceptance. The checked
OpenAPI snapshots come from the actual applications. The host launcher test prepares its simulated
parent group explicitly so BSD group inheritance does not invalidate the fixture; production
ownership rejection and the original no-change assertions remain intact.
The lower-level legacy native factory can omit deployment metadata and returns context=null; it
rejects supplied context assertions. The product compositions always provide metadata. A missing
context must remain unavailable to the frontend, with no inferred installation or command grant.

## Development checks

From the root, using the locked Node and pnpm versions:

```sh
pnpm install --frozen-lockfile
pnpm --filter @domus/frontend exec playwright install chromium
pnpm check:frontend
pnpm test:frontend
pnpm test
```

Application Vitest tests run in real headless Chromium with V8 measurement. All authored runtime,
including unimported modules, must reach 100% statements, branches, functions and lines globally and
per file. A separate filesystem inventory audits the summary. The fictional framework fixture and
Node policies retain their own measurements and artifacts. Application CI is a required CI Check
job on every PR update, including drafts and documentation-only changes.

The actual application import graph is checked alongside existing negative architecture fixtures.
Domain/Application remain independent of concrete adapters and frameworks. This initial model has
no DOM, storage, HTTP or framework dependency. See [development](development.md) for the other gates.
Model execution is separate from rendering, accessibility, integration, package and owner HA acceptance.

## Remaining delivery

Strict frontend HTTP adapters that fulfill the implemented server/context contract and base-relative
delivery remain required. The owned Lit UI
must demonstrate both locales, all primary states, accessibility, responsive layouts, Storybook and
both browser compositions. The all-domain first release, both targets and isolated channels remain
required. Follow the existing [identity](identity-household.md) and [setup](household-setup.md) contracts.
