# Development foundation

The documentation foundation was merged through [PR #3](https://github.com/vypdev/domus/pull/3).
[Issue #4](https://github.com/vypdev/domus/issues/4) starts M1 with real development tooling, tests and CI.
The issue #6 checkpoints introduce storage, pure identity policy, local authorization and session leases.
HA protocol adapters have provider/loopback tests and the standalone authentication API/CLI is wired.
Membership commands, product UI, Supervisor runtime, packages and channels remain pending.

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
The Node report measures the authored declarative frontend import policy: one executable configuration
statement, with no authored functions/branches. Its four reported metrics are enforced at 100%,
but this is not application UI coverage. Tests, generated dependencies and framework configuration
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
Node policy, Python architecture
contracts and local documentation links for every PR update, including drafts and documentation changes.
It also runs on develop/master pushes and merge-queue validation. There are no path filters or job
conditions hiding applicable suites. Actions are pinned to immutable commits and installs use lockfiles.

The final CI Check job always evaluates all five required job results. Missing, malformed, unexpected,
failed, skipped, cancelled or pending results prevent success. Only five explicit successful results pass.
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
