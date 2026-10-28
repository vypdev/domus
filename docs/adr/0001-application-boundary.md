# ADR 0001 — Modular application with a thin HA companion

- Status: Proposed
- Date: 2026-10-28
- Decision owners: Domus product and architecture reviewers

## Context

Both Supervisor App/Ingress and standalone Container are confirmed launch targets.
Domus needs its own complete UI and durable household business model.

## Decision

Propose one modular local server and a thin native HA companion integration.
Domain and application code depend on ports; frameworks and SQL remain adapters.
Python/FastAPI, SQLite and Lit/TypeScript/Vite are proposed, pending review.

## Alternatives and consequences

A custom integration alone shares too much complex runtime work with HA Core.
An App alone excludes standalone and native entity registration.
The hybrid adds packaging/identity work but gives both targets the same business core.
The gateway remains unchanged. No MCP is introduced.
