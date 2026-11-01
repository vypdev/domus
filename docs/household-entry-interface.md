# Household entry interface foundation

The development branch implements the pure entry decisions and setup-input model. The product
entry page, journal, controller, transport adapters and static delivery remain to be implemented.
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

The one-hour/eight-record/64-KiB journal, deliberate command recovery, generation-fenced controller,
strict adapters, server-owned context and base-relative delivery remain required. The owned Lit UI
must demonstrate both locales, all primary states, accessibility, responsive layouts, Storybook and
both browser compositions. The all-domain first release, both targets and isolated channels remain
required. Follow the existing [identity](identity-household.md) and [setup](household-setup.md) contracts.
