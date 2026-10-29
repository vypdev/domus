# Reference investigation

Audited 2026-10-28. Neither reference repository was modified.
Copilot source revision: f5e5a4cf9a80248994469cd88ad55eecab5b95ca.
Gateway source revision: 9d4e159182f7c955406c37fd372ee3ec50ed2b87.

## Copilot conventions actually inspected

| Source | Observed convention | Domus adoption |
|---|---|---|
| [Specification standard](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/specs/README.md) | Product contract, architecture, UX, configuration, numeric tests, acceptance and documentation | Unmodified reference copy plus proportionate prospective SDDs |
| [Template](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/specs/_template.md) | Twenty numbered English sections and explicit review metadata | Exact original headings and Draft status |
| [Product specification skill](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/.agents/skills/product-specification/SKILL.md) | Evidence first; pure rules, ports, bounded configuration, user states and review gates | Applied to authoring; no competing methodology |
| [Catalog validator](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/src/infrastructure/specification_catalog_validator.cjs) | SDK v1 statuses, real paths, unique ownership and generated catalog | Preserve proposed status; expose missing implementation evidence |
| [Draft consistency policy](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/src/domain/sdd_draft_consistency.ts) | Requirement/Behavior; case inventory/budget; Path/Change; reciprocal Requirement/Cases | Exact table shapes, full IDs and explicit created documentation paths |
| [Pre-branch guide](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/docs/issues/pre-branch-sdds.mdx) | Feature/contract-change clarification before first SDD branch commit | Existing documentation workflow for this foundation; no invented feature branch |
| [Specification lifecycle](https://github.com/vypdev/copilot/blob/f5e5a4cf9a80248994469cd88ad55eecab5b95ca/docs/development/specifications.mdx) | Update contract, tests, implementation and docs together | Ownership and lifecycle retained |

Observed SDK limitation: entrypoints/code/tests arrays must be nonempty even for proposed entries.
This product has none yet. The proposal does not disguise documents as code or change Copilot to bypass it.
SDD format consistency, catalog validity, branch readiness and product acceptance are different claims.

## Gateway patterns actually inspected

| Concern | Primary source and observation | Adopt / differ |
|---|---|---|
| Application packaging | [App config](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/addon/config.yaml), [deployment targets](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/deployment-targets.md): App plus standalone deployment, owned persistent data | Both are confirmed Domus launch targets |
| Backend | [Architecture](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/architecture.md), [HTTP composition](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/src/homeassistant_gateway/presentation/http.py): FastAPI entrypoints and semantic application ports | Reuse boundary principles; richer Domus domain and transactional ledgers |
| Frontend | [Design](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/frontend-design.md), [package](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/frontend/package.json): Lit/TS/Vite, public theme tokens, i18n, browser/architecture checks | Proposed stack, own household design; no private frontend imports |
| Auth and structured errors | [Security model](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/security-model.md): separate trust boundaries, bounded results, redaction and audit | Per-member Domus roles and technical service scope; no gateway token lifecycle work |
| HA discovery/actions | [Task/shopping guide](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/consumer/tasks-and-shopping-lists.md): services, native item UIDs and response contracts | Domus exposes its own authoritative entities/services; unrelated native lists are not silently mirrored |
| Jobs and persistence | Architecture describes process-local console jobs and SQLite adapters | Business scheduler/outbox are durable in Domus; restart-loss semantics are unsuitable |
| Channels | [Stable/Edge guide](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/docs/release-channels.md), [Edge config](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/addon-edge/config.yaml): distinct slugs, images, data and host ports | Adopt isolation, immutable source evidence and experimental designation |
| Development/testing | [CI](https://github.com/vypdev/homeassistant-gateway/blob/9d4e159182f7c955406c37fd372ee3ec50ed2b87/.github/workflows/ci.yml): backend, frontend, packaging and browser checks | Domus CI Check and owner-required maximum coverage; do not copy an 85% threshold |

The gateway channel guide contains historical branch statements that disagree with some source comments.
Domus will derive release sources from its actual installed branch configuration, not copy those comments.
Research establishes patterns, not deployed compatibility. The owner states the gateway is already integrated;
gateway installation, modification and MCP transport are out of scope.

## Official platform references

- [HA Apps](https://contributors.home-assistant.io/apps/) establishes the Supervisor-managed packaging boundary.
- [Ingress](https://contributors.home-assistant.io/apps/guides/ingress/) is the App UI transport reference.
- [Authentication API](https://contributors.home-assistant.io/core/internals/auth-api/) is the basis for individual HA identity.
- [Integration actions](https://contributors.home-assistant.io/core/integrations/actions/) guides public service registration and responses.
- [Calendar entity](https://contributors.home-assistant.io/core/entities/calendar/) and [to-do entity](https://contributors.home-assistant.io/core/entities/todo/) guide projections.
- [RFC 5545](https://www.rfc-editor.org/info/rfc5545/) guides fixed calendar recurrence.

These platform contracts require disposable-instance tests before supported-version claims.

## Additional UI comparison requested by the owner — 2026-10-29

Symphonia was inspected at revision f780ea378db1b80b67214647583157aee3a5a858. Its
[accepted stack ADR](https://github.com/vypdev/symphonia/blob/f780ea378db1b80b67214647583157aee3a5a858/docs/decisions/0005-lit-typescript-vite-ui.md)
selects Lit/TypeScript/Vite, the same direction as Gateway. Its
[visual/interactions ADR](https://github.com/vypdev/symphonia/blob/f780ea378db1b80b67214647583157aee3a5a858/docs/decisions/0004-home-assistant-native-ui.md)
adds owned presentation primitives and a Home Assistant-coherent visual contract without private frontend imports.
The [isolated build spike](https://github.com/vypdev/symphonia/blob/f780ea378db1b80b67214647583157aee3a5a858/docs/development/ui-lit-spike/README.md)
is limited evidence, not proof that the complete application UI or HA/browser matrix is implemented.
The owner selected this direction for Domus with Storybook and Playwright on 2026-10-29.

| Concern | Evidence / lesson | Domus contract |
|---|---|---|
| Framework | Gateway implements Lit/TS/Vite; Symphonia records the same accepted direction | Use the selected stack; do not copy dependency versions or assume a shared runtime component library |
| Presentation | Symphonia separates semantic tokens/primitives from feature controllers and clients | Domus owns HA-coherent components; Storybook isolates their states and Playwright exercises them |
| Host context | [Symphonia's evidence](https://github.com/vypdev/symphonia/blob/f780ea378db1b80b67214647583157aee3a5a858/docs/development/ui-spike/host-context-evidence.md) does not establish that theme, locale or identity are forwarded to App iframes | Validate any public source/origin/shape; preserve member/browser fallbacks and never use UI hints as authorization |
| Ingress and mobile | Relative Vite assets alone do not prove reload/deep-route behavior; safe-area padding has a host contract | Test non-root route reload and all request paths; apply safe-area insets once |
| Private HA controls | [Official component notice](https://contributors.home-assistant.io/blog/2026/03/25/frontend-component-updates-2026.4/) warns that built-in component APIs are unstable for extensions | No private imports, parent-DOM access or private host storage dependencies |

This comparison changes Domus design evidence and acceptance cases only. Neither reference project nor Copilot was modified.
