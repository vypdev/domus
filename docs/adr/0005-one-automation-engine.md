# ADR 0005 — One declarative automation engine with two editing levels

- Status: Accepted product direction by owner on 2026-10-29; detailed engine contracts remain Draft
- Date: 2026-10-29
- Decision owners: Domus product, architecture and security reviewers

## Context

The owner wants simple in-application rules by default and a complete optional advanced mode, both in the first release. HA must also consume Domus capabilities through native entities and services without gateway changes.

## Decision

Use one versioned declarative model and durable engine behind simple and advanced editors. The advanced editor adds bounded branching, repetition/parallelism, waits, simulation and inspectable traces. Both call the same authorized domain use cases; the HA adapter delegates to the engine where a stored rule is invoked.

Keep domain invariants in their owning modules. Run receipts, pinned rule revisions, durable waits, current permission checks and causal budgets define replay, edits, cancellation and partial recovery. The simple form preserves unsupported advanced fields and directs editing to advanced mode.

## Consequences and alternatives

Two unrelated rule engines would duplicate behavior and complicate recovery, so they are rejected. Arbitrary scripts and raw backend/network passthrough are outside this declarative contract. More combinations require meaningful schema, race, replay, loop, browser and recovery tests from first implementation. Numeric limits, action catalog and supported-version proof remain engineering gates before Ready for implementation.

Both modes are launch scope; this ADR does not authorize runtime implementation, merge or deployment. Copilot and the gateway remain unchanged.
