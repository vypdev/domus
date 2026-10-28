# ADR 0001 — Modular application with a thin HA companion

- Status: Accepted by owner on 2026-10-29; implementation verification pending
- Date: 2026-10-28
- Decision owners: Domus product and architecture reviewers

## Context

Both Supervisor App/Ingress and standalone Container are confirmed launch targets.
Domus needs its own complete UI and durable household business model.

## Decision

Use one modular local server and a thin native HA companion integration.
Domain and application code depend on ports; frameworks and SQL remain adapters.
The owner selected Python/FastAPI, SQLite and Lit/TypeScript/Vite on 2026-10-29, with one household per installation. Domus owns HA-coherent presentation components, Storybook fixtures and Playwright browser tests. Exact dependency versions, authentication, storage concurrency and the supported HA/browser matrix still require engineering evidence; this decision does not declare any implementation complete.

## Alternatives and consequences

A custom integration alone shares too much complex runtime work with HA Core.
An App alone excludes standalone and native entity registration.
The hybrid adds packaging/identity work but gives both targets the same business core.
The gateway remains unchanged. No MCP is introduced.
