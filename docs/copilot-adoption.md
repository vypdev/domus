# Adopting Copilot without changing Copilot

## Observed installation

Domus master initially contains the minimal README and installed Copilot resources at commit 8ee7e1a.
The repository profile enables documentation work through the installed documentation form, requires
Action-managed remote branches and declares pre-branch SDD. No SDD prerequisites exist on that baseline.

The owner prohibits edits to Copilot's repository, code, workflows, profiles, guides, templates and scripts.
Only an existing project-owned dependency preparation file may be considered when necessary:
the inspected candidate is .github/actions/copilot-verification-setup/action.yml, currently a failing placeholder.
No changes to it are part of this documentation package.

## Inherited specification contract

The original specs/README.md and specs/_template.md are included as unmodified reference copies from
Copilot revision f5e5a4cf9a80248994469cd88ad55eecab5b95ca. They do not replace installed Copilot resources.
Domus SDDs retain all twenty English headings. Section 4 declares Requirement/Behavior, section 14 contains
the exact numeric budget and case inventory tables, section 15 declares Path/Change, and section 17
provides the exact reciprocal Requirement/Cases table required by the audited consistency validator.
Every case is planned acceptance work, not a claim that tests exist.

## Catalog limitation

The initially audited SDK version-1 validator required nonempty entrypoints, code and tests arrays for every capability,
including status proposed. At that foundation snapshot Domus had no implementation files. The proposed catalog preserved
empty arrays and an explicit readiness blocker instead of referencing fake source or calling documents code.
The original validator is run unchanged against the package; failure is recorded in the validation evidence in docs/sdd-validation.md.
A passing draft-format check cannot establish gate readiness.

The truthful proposed-capability bootstrap limitation is reported in [Copilot issue #777](https://github.com/vypdev/copilot/issues/777), with a pinned-source reproducer. The separate opaque progress-assessment failure is tracked in [Copilot issue #774](https://github.com/vypdev/copilot/issues/774#issuecomment-6483788546). These reports are not evidence that the catalog caused the workflow's progress failure, and neither authorizes a local workaround or a Copilot edit.

Do not patch the validator, substitute a weaker schema, change capability status, register unrelated code,
or alter any Copilot configuration to conceal this result. Resolve the supported initialization route
with the maintainer before attempting a feature gate. The current documentation issue is not marked
contract-change and needs no synthetic feature issue.

## Contribution lifecycle

[Documentation issue #2](https://github.com/vypdev/domus/issues/2) is the single initial work item.
A maintainer adds in-progress after admission. The Action publishes the exact linked docs branch.
Only then may a contributor check out that ref and incorporate this prepared package. No remote branch
is created, renamed, force-pushed or deleted by this contributor.
A linked PR carries validation and unresolved decisions; maintainers own merge and deployment.

The specification foundation had no runtime package, pnpm task or project CI. Issue #4 now adds a development-tooling package, locked dependencies, tests and a separate project-owned CI Check workflow, documented in [development](development.md). Household application/runtime capabilities remain prospective. Commands in the unchanged upstream standard are not Domus commands unless the development guide verifies them. The original draft-check runner outside this repository remains a review aid and does not replace the Action's bundled authority.

The tooling checkpoint registered real delivery-quality evidence and reduced the original pinned validator's
errors from 33 to 30; those reports remain historical. On 2026-10-31, reviewed v3 revision
3e7ceea08e6131360e026937d1c0cc1b120472e0 accepted the truthful proposed catalog with zero errors.
The Action then published the issue #6 companion and verified its managed branch at
3fdf4f841e7e2f6d37f8ebfd4b8d80f1ce90090f. No manual branch or validation bypass was used.
The current storage checkpoint adds only actual partial platform evidence; statuses remain proposed/Draft,
missing entrypoints remain empty and HA/runtime acceptance is not inferred. Copilot stays unchanged.
