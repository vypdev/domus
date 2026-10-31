# Home Assistant app installation

Status: native Ingress authentication preview implemented; app packaging and installation proof
are being prepared. No production release is available. The complete household product remains
under development.

## Intended user journey

1. Add the published Domus app repository from Settings > Apps > Install app > Repositories.
2. Install Domus Edge for development, or the separately published stable app for production.
3. Start the app and select Open Web UI. Optionally enable its sidebar entry.
4. Use the existing Home Assistant session. There is no second Domus sign-in or password.

The independent Docker installation has a separate OAuth journey because it runs outside the
Supervisor. That journey is not an installation prerequisite for the HA app.

## Current native preview

The preview runs with `domus-ingress --channel edge` inside the Supervisor container. Configuration
supplies SUPERVISOR_TOKEN privately; no human enters or copies a token. The private listener accepts
protected requests only from the actual Supervisor peer, validates the Ingress base path and exact
subject header, and checks that human in Core. Forwarding headers, names and the transport account's
administrator privilege cannot grant the requesting person access.

The root page shows connection status, uses relative navigation and requires no browser cookie or
OAuth callback. The identity endpoint exposes only the requesting human's proof. Process health
is available to Supervisor and container loopback and is not a claim of HA availability. There are
no household commands, local read-grace sessions or business database in this preview. A failed fresh
proof blocks access. It is not complete M1, the product UI or a production compatibility claim.

The eventual app manifest must enable Ingress and Core API access, publish no host port, and keep
Stable and Edge as distinct apps with separate data. Core API access gives the container a technical
HA administrator credential; it must stay private and must never substitute for the human principal.

Official references: [Ingress authentication and relative paths](https://contributors.home-assistant.io/apps/guides/ingress/),
[repository installation and branch selection](https://contributors.home-assistant.io/apps/guides/repository/),
[Core API proxy permissions](https://contributors.home-assistant.io/apps/guides/communication/).
