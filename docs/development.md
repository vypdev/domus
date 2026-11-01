# Development foundation

The documentation foundation was merged through [PR #3](https://github.com/vypdev/domus/pull/3).
[Issue #4](https://github.com/vypdev/domus/issues/4) starts M1 with real development tooling, tests and CI.
The issue #6 checkpoints introduce storage, pure identity policy, local authorization and session leases.
HA protocol adapters have provider/loopback tests and the standalone authentication API/CLI is wired.
Explicit setup, own enrollment and household edits now have application-layer commands. The native
Ingress connection preview and immutable-source Edge package are installed and tested on the owner's HA.
Native persistent API wiring, console-approved recovery and manual snapshots are tested locally.
App packaging, restore activation, product UI and complete
Stable/Edge release acceptance remain pending.

## Reproduce the environment

Use Python 3.14.6, uv 0.11.29, Node 24.20.0 and pnpm 10.34.0. The Python and Node version files,
package-manager declaration and dependency locks record the tested baseline. Install those runtimes
through your normal local manager; setup does not require modifying Copilot or the gateway.

```sh
uv sync --frozen
pnpm install --frozen-lockfile
```

The Python tooling distribution is domus-tooling. The separate domus-server workspace distribution
contains the actual backend modules under backend/src/domus and has its own coverage gate.
The frontend workspace
currently declares its package boundary only; Lit/Vite application source and its own coverage gate
belong to the first frontend implementation. No empty application package is used as implementation evidence.

## Run the same checks as CI

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy tooling
uv run mypy backend/src
uv run pytest tests/python --cov=domus_tooling --cov-branch --cov-report=term-missing
uv run pytest tests/backend --cov=domus --cov-branch --cov-report=term-missing
pnpm check
pnpm test
uv run lint-imports --config architecture/python-tooling.ini --no-cache
uv run lint-imports --config architecture/python-application.ini --no-cache
uv run pytest tests/architecture
uv run domus-check docs
```

Python coverage includes all modules of domus_tooling, including modules not exercised by a test.
Coverage.py exposes executable statements/lines and branches here; both must reach 100%.
The Node report measures the authored frontend import policy and reusable coverage policy. Its four
reported metrics are enforced at 100% globally and per file. This is tooling coverage, separate from
the fictional framework fixture and future application UI coverage. Tests, generated dependencies and framework configuration
are distinct from runtime source. A source-inventory test rejects a new backend, UI or HA runtime
file until its own applicable coverage/architecture gate is registered.

## Architecture contracts

- architecture/python-tooling.ini checks the actual tooling package: pure CI policy cannot import its
  CLI/filesystem adapters, concrete I/O or framework modules, and modules remain acyclic.
- architecture/python-application.ini checks the actual backend and disposable negative fixture packages. Composition
  wires adapters; entrypoints and infrastructure are independent; application depends inward on domain.
  Inner layers cannot import HA, HTTP, SQL or concrete frameworks. Recursive cycle checks have an
  explicit depth budget of 100; the normal package layout is shallow. A deeper layout needs review.
- architecture/frontend.mjs is exercised by the real dependency-cruiser TypeScript parser. Domain and
  application cannot import outward layers/frameworks; presentation cannot import concrete adapters;
  type-only imports, cycles and unresolved imports are checked.

Fixture packages are owned test data, not shipped application modules or product implementation evidence.
The real domus graph is now wired into CI alongside its own tests. A future HA integration must add
its own scope. The inventory guard prevents runtime source from inheriting a tooling-only green result.

The selected TypeScript 6.0.3 is inside dependency-cruiser 18.7.0's inspected supported range,
>=2.0.0 and <7.0.0. The executable parser check fails if that support is lost during a dependency update.
See the primary [dependency-cruiser API](https://github.com/sverweij/dependency-cruiser/blob/v18.7.0/types/dependency-cruiser.d.mts),
[Import Linter contracts](https://import-linter.readthedocs.io/en/stable/contract_types/index.html),
[pytest-cov configuration](https://pytest-cov.readthedocs.io/en/stable/config.html) and
[Vitest coverage](https://vitest.dev/config/coverage).

## CI Check

The project-owned .github/workflows/ci_check.yml runs Python tooling, the separate backend suite,
Node policy, real frontend framework execution, Python architecture
contracts and local documentation links for every PR update, including drafts and documentation changes.
It also runs on develop/master pushes and merge-queue validation. There are no path filters or job
conditions hiding applicable suites. Actions are pinned to immutable commits and installs use lockfiles.

The final CI Check job always evaluates all seven required job results, including the container matrix.
Missing, malformed, unexpected, failed, skipped, cancelled or pending results prevent success.
Every required job must explicitly succeed. The container job builds and tests the exact Supervisor
app folder on native amd64 and aarch64 runners; it never publishes images or installs into live HA.
The workflow uses read-only repository permissions, does not persist checkout credentials and does not
publish artifacts to a release or deploy. Coverage reports are retained for seven days under the checked SHA.

29 installed Copilot resources have immutable SHA-256 fixtures. The existing dependency-preparation
action remains the owner's explicit exception; this task does not edit it or enable/change Copilot settings.
The local link checker parses Markdown links/images and does not fetch external URLs. Only the unchanged
upstream specification template's placeholder targets are excluded. Original Copilot format/catalog validation
remains separate: link success does not establish SDD gate readiness.

## Evidence and remaining work

The first tooling increment has 64 Python tests, 11 Node policy tests and 10 Python architecture fixture
tests. These 85 executed tests are separate from the 353 planned product acceptance cases.
[Tooling evidence](evidence/development-tooling.json) records exact scopes and metrics.
The first implementation commit, 8a1c8fbdc50960a124fc76bc16702638845a0606, passed all five jobs in [CI Check run 40800913976](https://github.com/vypdev/domus/actions/runs/40800913976). Every later head must pass independently; this recorded result does not transfer to new code.

Delivery-quality and platform-foundation register only their real partial evidence and stay proposed/Draft.
The identity capability now registers its partial pure/local evidence; other product domains retain
empty implementation evidence. Reviewed Copilot v3 revision
3e7ceea08e6131360e026937d1c0cc1b120472e0 resolves
[issue #777](https://github.com/vypdev/copilot/issues/777): truthful proposed capabilities may retain
empty implementation arrays. The current original validator accepts the catalog without changing
Copilot or manufacturing paths. Historical failure reports remain historical evidence.
The entire delivery-quality capability still needs complete application/UI coverage, real deployment/HA
contracts, Stable/Edge isolation and controlled Chrome evidence before acceptance.

The storage checkpoint has its own [architecture and limits](architecture-identity-storage.md),
[source-identified evidence](evidence/m1-storage-kernel.json) and
[current HA reference matrix](compatibility-home-assistant.md). It does not implement a human
authentication entrypoint, snapshot command or HTTP server yet.

The subsequent [identity-policy evidence](evidence/m1-identity-policy.json) records pure mappings,
permission precedence, transaction-bound authorization, schema 2 migration and bounded session leases.
Provider fixtures are not live HA acceptance. The [migration guide](migrations-identity-storage.md)
identifies the frozen schema 1 input and the fail-closed unconfigured-household state.

The [HA protocol adapters](ha-identity-protocol.md) use HTTP provider fixtures and ephemeral loopback
WebSocket servers. Local sandboxes that forbid listening sockets need permission for the backend
suite; no test contacts the owner's HA. [Protocol evidence](evidence/m1-ha-protocol.json) identifies
the reviewed Core blobs, fixed dependency versions and outstanding live/package journeys.

The [standalone authentication checkpoint](identity-household.md) now has strict API/CLI wiring,
single-use browser-bound attempts, private token refresh, safe logout and shutdown-race tests.
Use [configuration](configuration.md) and [operations](operations-identity-storage.md) for this current
surface. The import contract rejects both inner layers importing every declared concrete SDK,
filesystem/process I/O or global time/entropy source. Its expanded negative matrix has 39 fixtures.
FastAPI/Uvicorn are fixed runtime dependencies. httpx2 is a separate fixed development dependency
required by Starlette's current TestClient; the HA transport retains its independently tested HTTPX
version. No deprecated TestClient fallback or Copilot modification is used.

The [native HA preview](installation-home-assistant.md) composes existing Ingress/Core proof on a
private listener and serves an operational connection page without OAuth or its own browser cookie.
Its source-bound Edge package has a separate [package receipt](evidence/m1-app-package.json).
The owner selected native HA installation as the next dogfooding path after the independent browser
session return failed. The test OAuth grant was revoked successfully; this does not establish native
Ingress compatibility by itself. The subsequent
[native acceptance receipt](evidence/m1-native-ha-acceptance.json) records successful installation,
start, Open Web UI and normal reload of the exact Edge preview on the identified HA target.
Both deployment targets remain required for the first usable release.

The [household command checkpoint](household-setup.md) uses application ports for current human proof,
directory lookup, UTC clock, secure identifiers and IANA timezone validation. External preparation is
outside SQLite writer transactions. Its real-file tests cover one complete concurrent setup winner,
rollback, restart, current-authorization-before-replay and pending enrollment. The bounded HA batch
directory distinguishes confirmed ineligibility from source failure; malformed or duplicate records
cannot become partial success. [Source-identified evidence](evidence/m1-household-commands.json)
records the implemented scope and coverage. These commands are not in the installed preview image.

The next [member-administration checkpoint](evidence/m1-member-administration.json) adds explicit
activation, profiles/status/exception edits and last-administrator checks against current human facts.
It tests real SQLite interleavings, fresh actor reproof, local authority revocation, archived-linkage
preservation, rollback-free conflicts and same-key concurrent receipt reuse. Coverage includes the
complete authored backend; neither these use cases nor their later source are in the installed image.

The [policy-administration checkpoint](evidence/m1-policy-administration.json) adds revisioned
mapping/profile changes with preserved setup provenance and independent grants. A shared application
helper prepares bounded human facts for member and policy safeguards, with no framework imports.
Current local authority and inventory remain transactional. Source/audit corruption, lost authority,
source outage, stale state, rollback-free conflicts and restart/replay behavior have real-file tests.

The [household HTTP checkpoint](household-api.md) exposes local authorization/roster/policy/operation
queries and strict write DTOs. The standalone --database option wires the real session, private
directory, use cases and SQLite adapter. Tests include actual composed-runtime restart, channel
refusal, CSRF/origin/idempotency, ambiguous JSON refusal, HA outage read grace and credential
logout/expiry races. [Its evidence](evidence/m1-household-api.json) and
[published OpenAPI](contracts/household-api.openapi.json) identify the implemented surface.
Recovery and native persistent packaging/UI remained outstanding at that checkpoint.

The [native household API checkpoint](native-household-api.md) now wires the same services to real
SQLite through private Supervisor Ingress. Tests bind local leases and CSRF to installation/channel,
exact human, app path and the existing upstream session. They cover original-deadline outage reads,
fresh writes, rejection, restart, concurrent bootstrap and a selected ordinary HA user's independent
Domus administrator grant. Fixed configured origins prevent forwarding headers from selecting trust.
[Its evidence](evidence/m1-native-household-api.json) and
[published OpenAPI](contracts/native-household-api.openapi.json) record the current runtime.
Owned identity, recovery/snapshots and restoration are now packaged in Edge.3. The complete UI,
standalone companion and full deployment/live household acceptance remain pending;
[current owner evidence](evidence/m1-edge3-ha-acceptance.json) covers connection/reload/restart.

The [owned data checkpoint](owned-data-directory.md) now persists initialization/ready metadata and
automatic UUID/channel identity inside an existing private directory. Native --data-directory holds
its POSIX process lock through the listener lifetime. Real-file/process tests reject missing or empty
ready data, cross-channel adoption, unsafe files and interrupted metadata; a compatible v1 migration
preserves history. The package provisions only its private child before dropping privileges;
Edge.3 update/reload/restart now has bounded owner evidence. See [evidence](evidence/m1-owned-storage.json).

The [administrator recovery checkpoint](administrator-recovery.md) adds the pure bound lifecycle,
schema 3 migration, same-target fresh completion proof and a console-only approval command. Both
production HTTP compositions share the human routes. Tests exercise real SQLite races/rollback,
terminal confirmation in a separate PTY process, approval output uncertainty and native/standalone
request-to-completion journeys. [Evidence](evidence/m1-administrator-recovery.json) identifies source
and remaining live work. Recovery is packaged in installed Edge.3; live recovery was not exercised.

The [snapshot checkpoint](snapshots.md) adds pure metadata, semantic application ports and a private
SQLite backup/inspection adapter. Tests use real files, concurrent WAL changes, physical index damage,
corrupt records/manifests, incomplete publication, deadlines and both console source selections.
[Evidence](evidence/m1-snapshots.json) records the exact coverage and boundaries. Restore activation
and its treatment of newer replay history remain pending; the installed HA app is unchanged.

The standalone CLI now shares --data-directory and its durable UUID/channel lifecycle with the
native runtime. It validates provider/public origins before storage, initializes exactly once,
retains the lock through the listener and releases it even if credential cleanup fails. Tests verify
real household/original-operation restart, lost sessions, channel/cookie separation and console
attachment. [Evidence](evidence/m1-standalone-owned-storage.json) records this local composition
checkpoint; complete standalone deployment and owner browser acceptance remain pending.

## Frontend framework infrastructure

[Issue #9](https://github.com/vypdev/domus/issues/9) establishes actual framework execution with a
fictional fixture in tests/fixtures/frontend-toolchain. It is a development workspace, outside
frontend/src, with no household, HA, authentication or release behavior. Issue #8 still owns the
unimplemented household interface and its own product tests.

The workspace locks Lit 3.3.3, Vite 8.3.5, Storybook/web-components-vite 10.6.5,
Vitest/coverage-v8/browser-playwright 5.0.5, Playwright 1.64.1 and TypeScript 6.0.3.
It uses the existing Node 24.20.0/pnpm 10.34.0 baseline. Run these commands after the frozen install:

```sh
pnpm --filter @domus/frontend-toolchain exec playwright install chromium
pnpm check:frontend-toolchain
pnpm test:frontend-toolchain
pnpm build:frontend-toolchain
pnpm test:frontend-browser
pnpm test:frontend-guards
```

CI installs Chromium with its Linux dependencies using --with-deps. Local environments must provide
Python 3 for the disposable static Storybook server. Loopback socket restrictions require permission
for browser/component tests; these commands do not contact the owner's HA. Ports 56171 and 56172
are fixture-only, refuse existing listeners and are managed by Playwright. Run browser and guard
commands sequentially, after both builds. The guards inject owned temporary negative fixtures and
remove them in finally blocks. They also verify server cleanup after a deliberate browser-test failure.

The reusable tooling/frontend-coverage.mjs policy includes unimported JS/TS runtime extensions and
requires 100% lines, statements, functions and branches globally and per file. The independent source
inventory check rejects missing files or supported metrics. Real negative executions add uncovered
JS and TS modules and remove a branch metric from a produced report; both commands must fail.
An empty fixture report cannot establish support. Policy coverage, fixture coverage and future product
coverage have separate scopes and artifacts. Declaration files are type-checked, not executable runtime.

Both TypeScript projects check owned code strictly. Runtime/configuration/tests use skipLibCheck:false.
Storybook 10.6.5's third-party declarations have TS2578/TS2344 errors with TypeScript 6.0.3; only
the catalog project uses skipLibCheck:true for dependency declarations. Owned runtime, stories and
Storybook configuration remain strictly checked. The guard deliberately supplies an invalid owned
story title and requires TS2322. No vendor declaration or Copilot resource is patched.

The component test exercises actual Lit DOM state, reflected ARIA state and composed bubbling events.
Four Playwright journeys exercise the built Vite entry and actual built Storybook story at 320px and
1280px: keyboard focus, Enter/Space activation, accessible button names, 44px target height, containment
and absence of page errors. This is bounded fixture accessibility evidence, not a full product audit.

[Source-identified evidence](evidence/frontend-toolchain.json) distinguishes local commands, coverage,
builds and browser assertions. Current-head hosted CI/Bugbot are separate PR gates. Fixture output
is not a Domus installation, product UI, native Ingress/standalone OAuth proof, owner Chrome
dogfooding or evidence for the 48 proposed household-interface cases. Stable/Edge and both deployment
targets retain their own pending acceptance obligations.

## Task execution backend

Issue #13 has an Action-published [backend companion](../specs/task-execution-foundation.md).
The current source implements immutable task rules, typed policy/definition/occurrence/cycle
repositories, schema-6 migration/checkpoint integration, current authority and durable creation,
assignment, claim, progress, completion, verification and reopening commands, plus policy, definition,
occurrence and dependency editors. Application queries now expose bounded definitions/occurrences,
current detail/action hints, restoration-aware history and own-operation lookup. Both business compositions now expose task HTTP behind their existing session, Origin and CSRF
boundaries. Material intents/settlement, dependency-review projections and actual consumers remain
incomplete.

Domain never authenticates or authorizes requests. TaskAccess rereads current active membership,
identity mapping, profile/member rules and stored assignment inside the caller transaction. Claim
permission is separate from assigned completion. On-behalf attribution requires its own grant;
a restricted actor cannot omit its own participation. Only the submitting actor supplies current
HA proof; another performer retains its local profile instead of an assumed external administrator
source. Approval uses current adult permission and the original cycle's participation rule.

TaskCommands obtains fresh proof before SQLite and uses AtomicCommands to commit state, original
receipt, audit and one source event together. Current grants precede receipt disclosure; new-work
preconditions follow it. First creation initializes absent defaults in that same write transaction.
Assignments accept at most 32 distinct active household members; self-claim is exclusive for
available work. Completion snapshots actual performers, policy revisions and performed/recorded
UTC times. Pending/rejected verification cannot satisfy approved-work gating; the performed default
also accepts pending approval. Required subtasks use the same explicit gate. Approval does not close
a cycle. Reopen closes it without erasing facts or automatically reopening completed dependents.
Source events identify the full cycle and causal revision, while consumer delivery remains explicitly
unconfirmed. They do not prove ledger compensation, stock movement or a finished review projection.

TaskQueries receives a server-proven human or valid outage read lease. Every page rereads local
membership and task-read authority in one read transaction. Policy reads return revision zero and
documented defaults when absent, without creating records. Lists return summaries with 25 items by
default and at most 100, using one lookahead row. Detail resolves current rules, immutable work and
actual dependency/cycle facts through the shared task_facts readers. Allowed actions describe current
self-performance/state/permission possibilities; every write still obtains fresh proof and rechecks.

The outer TaskCursor signs bounded keyset positions with HMAC-SHA256 and an injected process key.
Tokens expire after five minutes by default and bind account, installation, channel, household, query,
filters and page size through a context digest. A restart/key change may require refreshing a list.
Pagination is not a cross-page snapshot: concurrent edits may change later pages. No tokens contain
raw HA identifiers or grant write authority.

Task history merges at most two bounded SQL pages of current and retained evidence by durable outbox
position. Current retained projections appear once; historical effects remain explicitly absent and
their delivery suppressed. Shared history reveals local member IDs and selected facts, without raw
HA identities or canonical requests. Own-operation reads require current read/own-operation grants
and reconstruct original command authority from matching immutable request/result/event evidence,
including configuration and on-behalf scope. They never execute retained requests. Outbox
acknowledgement remains separate from unimplemented consumer acceptance.

Typed requests live in task_requests and command authorization is shared in task_authorization;
task_commands re-exports its established request names. Policy revision zero initializes absent
defaults, and positive revisions update existing configuration under administrator authority.
Definition edits preserve existing occurrence snapshots. Omitted overrides preserve their values;
explicit replacement/reset needs configuration authority even on replay. New occurrences snapshot
the current definition and reject paused/archived parents. Dependency edits require management and
nonterminal work, and validate every household graph page before writing. Real opposite-edge races
cannot commit a cycle. Source results retain dependency IDs without rewriting completed history.

SQLite owns transaction/foreign-key/CAS enforcement and strict versioned record decoding. It rejects
unknown/missing/future data without invented defaults. Scoped deferred foreign keys bind both sides
of the active cycle and revision. Initialization migrates frozen schemas 1–4 atomically; the independent
schema-4 input retains current/historical operation evidence, and earlier fixtures remain byte-unchanged.
Snapshot inspection checks all pages, references, DAG and cycle facts. Offline activation restores
older business state while retaining later receipts as processed; production command replay cannot
reapply restored-away lifecycle or editor changes.

Run the focused source contracts, then the complete backend coverage command:

```sh
uv run pytest tests/backend/test_task_values.py tests/backend/test_task_policy.py tests/backend/test_tasks.py
uv run pytest tests/backend/test_task_authorization.py tests/backend/test_identity_policy.py
uv run pytest tests/backend/test_task_commands.py tests/backend/test_task_execution_commands.py tests/backend/test_task_restoration.py
uv run pytest tests/backend/test_task_edit_commands.py
uv run pytest tests/backend/test_sqlite_tasks.py tests/backend/test_sqlite_task_integrity.py
```

Tests use real SQLite files and controlled concurrent writers. Isolated repository checks, owned-store
migration/activation and explicit broken-port fixtures have distinct scopes. HA proof is labeled fake;
no owner HA, product browser UI, packaged adoption or real consumer acceptance is implied. Full-suite
WebSocket fixtures need disposable loopback listeners; sandbox restrictions require permission for
those adapters rather than skipping them. The whole authored backend source enters line/branch
coverage immediately, including unimported files. The complete dependency graph remains mandatory.
[Source-identified evidence](evidence/task-execution-foundation.json) records current measurements,
original pinned SDD/catalog provenance, historical checkpoints and incomplete acceptance.


Task HTTP requests use strict bounded wire models in task_dto, mapped to typed application requests.
The shared task router serializes transport-independent output records at the outer boundary, with
actual composed OpenAPI snapshots for both deployments. Native task GET queries accept bounded,
nonduplicate parameters while retaining the original peer/header policy; other native routes retain
their existing query rules. The authentication-only preview does not acquire business task routes.
See the [task execution guide](tasks/execution.md) for payloads, defaults, original-key recovery,
restoration and the explicitly unsupported material fields. The task-specific own-operation route
rechecks original authority and prioritizes historical suppression over old outbox acknowledgement.


## Task material model and semantic processor

The material model now keeps canonical amounts, Inventory-owned binding snapshots and cycle-bound
intent state. Quantities are nonnegative canonical strings with at most 12 integer/six fractional
digits and no sign/exponent/zero aliases. Bindings additionally constrain unit precision. No Tasks
code calculates stock deltas. Missing actual quantity remains pending_recording; explicit zero is
not_used and cannot construct a movement request. Separate recording never auto-posts at completion.

The processor delegates reference resolution and effects to transaction-local Inventory semantics.
Its authority port must reread current grants and return a local member ID; prior authorization is
only an immutable source fact. Ordinary missing authority may retain valid completion usage; explicit
post/correct/dismiss requires current authority. Pending Inventory results certify no new movement.
UnavailableTaskInventory cannot resolve a catalog reference or confirm any stock effect.

Resource revision guards optimistic concurrency; effect revision changes only with desired quantity.
The source key excludes current actor/pending metadata and binds the full target/source effect.
Corrections preserve original submitted quantity and the last confirmed total until actual Inventory
confirmation. A correction needs new movement/operation identities; returning to the already
confirmed amount needs no new movement. Dismissal cannot erase confirmed consumption. Exact proof
replay is inert, and foreign/stale/conflicting proof cannot overwrite a later intent.

The pure processor still needs command integration; task write routes reject material fields.
SQLite material persistence and read DTOs are now implemented as described below. No stock ledger or
real-consumer acceptance is claimed. Required next work:

- Extend original canonical requests compatibly. Omitted new
  material fields must retain old request fingerprints; explicit replacement/clear stays distinct.
- Connect the persisted intent transitions to the one writer/receipt/audit boundary. Recording
  plus confirmation and correction plus confirmation can each advance resource revision twice; store
  those transitions atomically rather than assuming every final projection advances exactly once.
- Bind actual current task/material authority and transaction-local Inventory semantics. Providers
  must not perform network I/O or independent commits under that writer.
- Wire adjustable completion usage and explicit settlement in both HTTP compositions, truthful
  current/historical outcomes, concurrency/replay/rollback and actual migration/restoration tests.
  Map quantity values to canonical wire strings; keep bounded compact outcomes in receipt/event
  documents and full intent/binding records separate. Resolve admission unavailability explicitly;
  ordinary consumer unavailability after valid performance remains a pending outcome.
- Keep real Inventory/Points/recurrence/review projections and full product UI/deployment acceptance
  separate until their owning implementations supply evidence.


## Material persistence and read projection

Schema 6 adds cycle/line-unique material intents, scoped foreign keys, immutable submission guards,
strict versioned codecs and exact revision CAS. The unit owns the transaction; material repositories
never commit separately. Reopening a cycle retains its physical consumption facts. Checkpoint
inspection verifies each intent against the original occurrence line, cycle, recorder, performed and
recorded times and recording policy. Altered/missing source lines or facts fail closed.

Definition/occurrence storage documents use explicit version 2. Migration translates exact version-1
records to empty material lists; normal current reads do not guess missing fields. Schema 1–5 inputs
remain supported. The frozen v5 SQL comes from immutable 17ea907, not the new implementation, and
preserves an approved closed cycle plus restored-away completion. Migration retains receipts, audit,
source events, cycles and retained-operation records byte-for-byte. The original completion can be
retried through TaskCommands without allocation or re-execution. DDL and document failures roll back.
Actual offline activation migrates only its prepared target; source/checkpoint bytes remain intact.

Read responses use outer DTOs so planned quantities appear as canonical strings such as "0.25".
Both composed OpenAPI snapshots preserve existing paths, security and schema values while adding
TaskDefinition.materials and two response schemas. The domain has no Pydantic/FastAPI dependency.
Material write DTOs, explicit settlement commands and real Inventory acceptance still require the
next integration; SQLite and labeled confirmation fixtures do not establish actual stock movements.
