# Verification and acceptance plan

The SDD inventory contains 281 distinct planned cases across eleven capabilities.
The counts are derived from concrete observable scenarios and are minimums; no application tests have run.
Formatting, catalog metadata, branch readiness and working product acceptance are separate gates.

## From the first source file

Write meaningful behavior tests with each implementation. Enforce 100% supported first-party line, statement,
function and branch metrics separately for backend, frontend and integration code.
Do not mask untested paths with broad exclusions or count generated/third-party code as authored coverage.
Architectural rules, schema validation, permissions, replay/races and recovery are executable checks from the start.
Use deterministic clocks, IDs, bounded provider fakes and injected transaction failures.

The 2026-10-29 owner decisions add concrete cases for role-default verification, Ingress/host-context boundaries, configurable points allocation and actual-total reversals, optional external product lookup, recurrence anchored to actual work with per-task successor timing, and one automation engine with both editors. Its 42-case floor covers schema/editor round trips, permissions, durable waits/replay, partial recovery, resource/loop budgets and target/channel isolation. Case IDs, per-area budgets and reverse requirement mappings are regenerated together before running the unchanged original Copilot consistency functions.

## CI Check contract

A project-owned workflow named CI Check runs for opened, reopened, synchronized and ready-for-review PR heads;
draft PRs still run tests. Do not use path filters to skip suites. Merge-queue validation is included if enabled.
Run backend/domain, frontend, HA contract/integration, migration/security, architecture, docs, localization,
browser E2E and both-target/channel packaging suites. The aggregate cannot pass if a required job is missing,
unexpectedly skipped, failed or cancelled. Record the exact checked revision and coverage reports.

PR code runs without publication credentials. Persistent self-hosted runner execution requires the repository's
trusted-PR policy; a skipped untrusted-fork run is not passing evidence. Provision toolchains in the job
that executes tests. The existing Copilot files remain unchanged.

## Real environment evidence

Use disposable HA for automated integration tests. Use the owner's Google Chrome/local HA authorization
for controlled dogfooding of the implemented experimental artifact, across all domain workflows,
mobile/narrow layouts, themes, keyboard and screen-reader order. Record artifact SHA/digest, target,
channel, test data IDs, outcomes and cleanup. Screenshots supplement written semantic results;
browser success does not replace test coverage.

## First integrated release gates

Both deployment targets and Stable/Edge isolation pass the same business fixtures.
Cross-domain maintenance/material/receipt/points scenarios reconcile ledger totals and visible states.
Failure and compensation paths remain understandable. Documentation and actual schemas agree.
Every material decision is resolved before the owning SDD becomes Ready for implementation.
No release, production install or promotion is authorized by this package.
