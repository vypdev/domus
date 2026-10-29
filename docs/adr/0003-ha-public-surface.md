# ADR 0003 — Native HA entities and services, no new MCP

- Status: Proposed
- Date: 2026-10-28
- Decision owners: Integration and security reviewers

## Context

The owner confirms the existing gateway is already integrated and will consume Domus capabilities through HA.

## Decision

Expose bounded native entities, response services and events. Use stable registry IDs and instance/channel selection.
Route mutations through the same domain use cases as the UI. Verify individual HA identity or use narrow technical grants.
Rich queries use structured responses, not unbounded entity attributes.

## Alternatives and consequences

A second MCP duplicates the owner's ecosystem and is excluded.
An unrestricted backend proxy bypasses semantic contracts and is rejected.
A native surface needs HA version/identity tests but gives UI, automations and existing MCP a shared product contract.
