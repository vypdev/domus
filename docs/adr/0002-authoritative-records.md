# ADR 0002 — Domus owns domain facts and immutable ledgers

- Status: Proposed
- Date: 2026-10-28
- Decision owners: Domain and data reviewers

## Context

Tasks need occurrences and history; purchases need physical receipt; stock and points need correction/replay integrity.

## Decision

Propose Domus as authority for its records, with separate definition/occurrence and purchase/receipt facts,
immutable stock and points ledgers, operation receipts and transactional outbox/inbox boundaries.
HA views are projections. Unrelated native HA lists are not competing stores.

## Alternatives and consequences

A mutable stock/points integer loses auditability. Bidirectional uncontrolled mirroring creates ownership conflicts.
Ledgers add projection and compensation work, but make retries, reopening and restores explainable.
This does not require rebuilding every business record from events or introducing a distributed broker.
