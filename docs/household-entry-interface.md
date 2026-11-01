# Household entry interface foundation

The development branch implements pure entry/setup decisions and the bounded request journal with
its owned sessionStorage adapter. The product entry page, controller, HTTP adapters and static
delivery remain to be implemented.
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
to 128. Blank, control-character and unpaired-surrogate input receives a field error without changing
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
receipt or justify a new request key. The controller and real lost-response/server-commit journeys
remain to be wired and tested; current adapter tests use simulated receipts plus actual isolated
Chromium sessionStorage, without contacting the owner's HA.

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

Deliberate command recovery in the generation-fenced controller, strict HTTP adapters, server-owned
context and base-relative delivery remain required. The owned Lit UI
must demonstrate both locales, all primary states, accessibility, responsive layouts, Storybook and
both browser compositions. The all-domain first release, both targets and isolated channels remain
required. Follow the existing [identity](identity-household.md) and [setup](household-setup.md) contracts.
