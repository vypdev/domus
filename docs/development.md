# Development foundation

The documentation foundation was merged through [PR #3](https://github.com/vypdev/domus/pull/3).
[Issue #4](https://github.com/vypdev/domus/issues/4) starts M1 with real development tooling, tests and CI.
The household application, HA authentication, product UI, deployment packages and channels remain unimplemented.

## Reproduce the environment

Use Python 3.14.6, uv 0.11.29, Node 24.20.0 and pnpm 10.34.0. The Python and Node version files,
package-manager declaration and dependency locks record the tested baseline. Install those runtimes
through your normal local manager; setup does not require modifying Copilot or the gateway.

```sh
uv sync --frozen
pnpm install --frozen-lockfile
```

The Python tooling distribution is domus-tooling, not the application server. The frontend workspace
currently declares its package boundary only; Lit/Vite application source and its own coverage gate
belong to the first frontend implementation. No empty application package is used as implementation evidence.

## Run the same checks as CI

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy tooling
uv run pytest tests/python --cov=domus_tooling --cov-branch --cov-report=term-missing
pnpm check
pnpm test
uv run lint-imports --config architecture/python-tooling.ini --no-cache
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
- architecture/python-application.ini is exercised against disposable fixture packages. Composition
  wires adapters; entrypoints and infrastructure are independent; application depends inward on domain.
  Inner layers cannot import HA, HTTP, SQL or concrete frameworks. Recursive cycle checks have an
  explicit depth budget of 100; the normal package layout is shallow. A deeper layout needs review.
- architecture/frontend.mjs is exercised by the real dependency-cruiser TypeScript parser. Domain and
  application cannot import outward layers/frameworks; presentation cannot import concrete adapters;
  type-only imports, cycles and unresolved imports are checked.

Fixture packages are owned test data, not shipped application modules or product implementation evidence.
When the real domus or HA integration package is introduced, wire its real graph into CI alongside its
own tests. The inventory guard prevents that source from silently inheriting a tooling-only green result.

The selected TypeScript 6.0.3 is inside dependency-cruiser 18.7.0's inspected supported range,
>=2.0.0 and <7.0.0. The executable parser check fails if that support is lost during a dependency update.
See the primary [dependency-cruiser API](https://github.com/sverweij/dependency-cruiser/blob/v18.7.0/types/dependency-cruiser.d.mts),
[Import Linter contracts](https://import-linter.readthedocs.io/en/stable/contract_types/index.html),
[pytest-cov configuration](https://pytest-cov.readthedocs.io/en/stable/config.html) and
[Vitest coverage](https://vitest.dev/config/coverage).

## CI Check

The project-owned .github/workflows/ci_check.yml runs Python tooling, Node policy, Python architecture
contracts and local documentation links for every PR update, including drafts and documentation changes.
It also runs on develop/master pushes and merge-queue validation. There are no path filters or job
conditions hiding applicable suites. Actions are pinned to immutable commits and installs use lockfiles.

The final CI Check job always evaluates all four required job results. Missing, malformed, unexpected,
failed, skipped, cancelled or pending results prevent success. Only four explicit successful results pass.
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
Current-head GitHub execution must pass independently of local results.

The delivery-quality catalog entry registers only existing tooling/CI evidence and stays proposed/Draft.
Other capabilities retain empty implementation evidence. The original SDK validator still reports the
remaining missing evidence; this is not a workaround for [Copilot issue #777](https://github.com/vypdev/copilot/issues/777).
The entire delivery-quality capability still needs application coverage, real deployment/HA adapter
contracts, Stable/Edge isolation and controlled Chrome evidence before acceptance.
