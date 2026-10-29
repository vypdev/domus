# ADR 0004 — Tests from the first implementation and isolated channels

- Status: Proposed implementation; owner requirements confirmed
- Date: 2026-10-28
- Decision owners: Quality and release reviewers

## Context

The owner requires Clean Architecture, maximum test coverage, Stable/experimental channels and CI Check on each PR update.

## Decision

Enforce 100% supported first-party coverage metrics with meaningful behavior assertions and architecture checks.
Use a new project-owned CI Check workflow and separate Stable/Edge credentials, storage and HA identities in both targets.
Use immutable source/image evidence and controlled Chrome dogfooding at the authorized local HA.

## Alternatives and consequences

Copying the gateway's lower coverage threshold would violate the new requirement.
A shared Stable/Edge DB would make experiments production mutations and is rejected.
More fixtures and packaging checks are required. Copilot remains unchanged; release remains explicitly authorized.
