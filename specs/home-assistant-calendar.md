# Register the native Home Assistant calendar for Domus

- Status: Draft
- Catalog capability: home-assistant-surface

## 1. Executive summary

Add an opt-in, read-only native calendar in Home Assistant Core for planned and due Domus events. The integration provides one calendar entity per Domus installation and channel, with bounded reads and stable identity across same-source reconfiguration.

## 2. Problem, current behavior, and evidence

Domus already exposes an authorized calendar projection for current human sessions, but the selected owner does not establish a Core calendar config entry or a narrowly scoped installation read path. The compatibility matrix at `docs/compatibility-home-assistant.md` pins Core 2026.10.4 as a reference; it does not demonstrate native calendar acceptance. The existing Home Assistant surface in `specs/home-assistant-surface.md` remains the owning contract. This companion adds only the native calendar increment; the owner and its cases remain unchanged. The separately pinned owner preview is not evidence of acceptance for this increment.

## 3. Actors, surfaces, and terminology

The Domus operator enables the feature by configuring a SHA-256 digest for a randomly generated calendar bearer containing the installation UUID and channel. A Home Assistant administrator supplies the endpoint and bearer through Core’s configuration flow. Calendar viewers see projected planned and due events. Source identity means the Domus installation UUID plus channel; the Core entity identity remains stable when an entry is reconfigured for that same source.

## 4. Goals, non-goals, and fixed invariants

The four companion requirements cover one read-only calendar entity per installation and channel, duplicate-source denial and same-source identity retention; narrowly scoped, revocable installation access on the dedicated planned/due read path; preservation of projected UIDs, all-day dates, resolved timestamp offsets and half-open overlap; and bounded reads with explicit pending and unavailable states, ordinary retry and polling cleanup on unload. These constraints are exercised by configuration and identity checks, access-isolation checks across both Domus compositions, event-semantic checks, and read-lifecycle checks.

Operator opt-in is required. The calendar bearer is distinct from human sessions and the Supervisor token. Only planned and due pages are permitted on the dedicated bearer endpoint. Rotation or revocation takes effect after changing or removing the configured digest and restarting Domus; Core reconfiguration supplies the replacement bearer. Preserve existing human-session and Ingress boundaries.

Poll once per minute for the next 31 days. Limit requested ranges to 90 days, pages to 100 events, and a complete read to 1,000 events. Expired cursors, failed pages, malformed pages or exhaustion make the read unavailable; they must not yield a partial calendar presented as empty. For pending projection, retain known events with pending status; if no known event intersects the requested range, report unavailable. Preserve projected UIDs, ISO all-day dates and aware timestamps with resolved offsets. Display date-only events as one all-day date and timed occurrences as one-minute markers with an exclusive end.

This increment supports standalone use over its configured HTTPS endpoint and Supervisor use over a separate unpublished private port. Core 2026.10.4 must be exercised against both Domus compositions; later Core versions need separate qualification, with no runtime version ceiling. No mutation, historical-completion calendar, bidirectional synchronization, other Home Assistant entities or services, gateway change, release, live installation, deployment or promotion is in scope.

| Requirement | Behavior |
| --- | --- |
| domus-native-calendar-R1 | Register one read-only calendar entity per installation and channel; duplicate entries are denied and same-source reconfiguration preserves entity identity. |
| domus-native-calendar-R2 | Use a revocable, narrowly scoped installation bearer only on the dedicated planned/due read path; preserve the current Ingress and human boundaries. |
| domus-native-calendar-R3 | Preserve projected event UID, all-day dates, resolved timestamp offsets and half-open interval overlap. |
| domus-native-calendar-R4 | Bound polling and range queries, distinguish pending and unavailable results, retry normally and stop polling on unload. |

## 5. Current versus proposed product journey

The retained `home-assistant-surface` contract and recurrence/calendar specifications remain authoritative for their existing journeys and cases; this companion adds only the native planned/due calendar path.

- **Current:** Domus already has an authorized, bounded calendar query and a Home Assistant projection for planned, due, performed, and verified facts. The query requires human task-read authorization, and the projection preserves event identity and timing. The repository has no selected-tree calendar integration paths for this proposal; the listed integration and adapter paths are prospective creates, not existing functionality. See `backend/src/domus/application/calendar_queries.py` and `backend/src/domus/application/ha_calendar_projection.py`.
- **Configure:** An operator opts in by configuring a digest for a random installation bearer containing the Domus installation UUID and channel. A Home Assistant administrator submits the endpoint and bearer through Core's config flow. Duplicate source identity is denied; reconfiguration must verify the same source and retain the entity identity (domus-native-calendar-C01, domus-native-calendar-C02).
- **Read:** One read-only calendar entity per installation/channel polls planned and due events over a bounded upcoming window. The dedicated installation authorization permits only that planned/due read path. Existing human session and Ingress boundaries remain unchanged, and the Supervisor token is not reused (domus-native-calendar-C03, domus-native-calendar-C07).
- **View and recover:** Core displays stable event UIDs, date-only events as one-day all-day entries, and timed points with their resolved offset and a one-minute exclusive end. Pending known events remain visibly pending; failed, exhausted, malformed, or empty pending reads are unavailable rather than falsely empty. Polling retries normally and stops on unload (domus-native-calendar-C04, domus-native-calendar-C05, domus-native-calendar-C06).

Text equivalent: operator configures a digest -> administrator registers and verifies the source -> Core reads bounded planned/due pages -> viewers see faithful events or an honest pending/unavailable state.

## 6. Functional behavior and state model

The existing calendar query accepts a `CalendarRange`, filters, a page limit from 1 through 100, and a cursor bound to the query context. It returns projected entries, count, next cursor, and pending status; authorization and cursor checks are part of that path (`backend/src/domus/application/calendar_queries.py`, `CalendarQueries.page`). The existing Home Assistant projection maps each entry's identity, title, kind, state, date or resolved timestamp into an event and disables external synchronization (`backend/src/domus/application/ha_calendar_projection.py`, `ha_calendar_projection`). This companion specifies a distinct installation-authorized adapter to those planned/due facts; it does not change the retained human query contract.

The Home Assistant entry moves through absent, configured, ready, pending, unavailable, and unloaded states. Successful reads refresh the entity; known events in a pending projection retain pending status. A pending read with no known event intersecting the requested range, a source failure, malformed response, expired cursor, page failure, or any exhausted bound yields unavailable, never a fabricated empty calendar. Normal scheduled polling retries recoverable failures. Unload cancels scheduled polling and entry listeners.

Poll once per minute for the next 31 days. Bound each requested range to 90 days, each page to 100 events, and a complete read to 1,000 events. Exceeding a range or total-read limit, or encountering any failed page, fails the complete read rather than publishing partial results. Preserve the projected UID, ISO date or aware timestamp, resolved offset, and half-open interval overlap. A date-only event occupies that calendar day and ends at the following date exclusively. A timed point is represented as a one-minute marker with an exclusive end. No source writes or unsupported native mutations are exposed.

The dedicated bearer is accepted only for planned/due calendar pages. Missing, malformed, duplicate, old, wrong-scope, or otherwise unauthorized credentials and writes are denied without event data. Human/Supervisor credential substitution and unauthorized historical-event requests likewise reveal no event data. Both Domus compositions must enforce the same boundary. The bearer is generated for the installation UUID and channel; only its SHA-256 digest is configured in Domus. Digest comparison is constant-time. Rotation or revocation takes effect after the operator changes or removes the digest and restarts Domus; reconfiguration supplies the replacement bearer and preserves identity only after same-source verification. These observable behaviors are covered by domus-native-calendar-C02, domus-native-calendar-C03, domus-native-calendar-C05, domus-native-calendar-C06, and domus-native-calendar-C07.

## 7. User-facing configuration

Configuration is explicit and opt-in. The operator generates a random calendar bearer containing the immutable installation UUID and channel, configures only its SHA-256 digest in Domus, and restarts Domus to apply it. Home Assistant's config flow accepts the configured endpoint and bearer; the bearer is masked in the UI and excluded from diagnostics. The same installation/channel cannot be added twice. Reconfiguring an entry requires verification of the same source identity and retains the existing entity identity. Replacing or removing the digest and restarting Domus rotates or revokes access; the Home Assistant entry must then be reconfigured with the replacement bearer.

Standalone connections require HTTPS. The Supervisor deployment uses a separate unpublished private listener on the Supervisor network; the normal Ingress listener and human session flow remain unchanged. The gateway credential is not shared. Core 2026.10.4 is the required qualification target for both Domus compositions; later Core versions require separate qualification. The selected compatibility matrix pins the reference version but does not establish native-calendar acceptance (`docs/compatibility-home-assistant.md`). No runtime version ceiling is introduced.

The operator-facing setup and recovery instructions should explain endpoint selection, digest opt-in, duplicate rejection, rotation, revocation, pending and unavailable states, and the requirement to use HTTPS for standalone access. Do not expose credential values or complete secret-bearing URLs in errors or diagnostics. No Domus credential-management UI is part of this increment.

## 8. Clean Architecture design

The Domus application reuses the authorized calendar query and the existing Home Assistant projection semantics; the new installation authorization is a separate, narrowly scoped adapter contract. Application and domain code do not import Home Assistant. The HTTP entrypoint validates transport input and installation credentials, then invokes the planned/due query path. Composition supplies the configured digest, installation/channel identity, endpoint settings, and runtime wiring for both the private Supervisor listener and standalone HTTPS origin. The Home Assistant integration owns config flow, source identity verification, event mapping, polling, and unload cleanup; it does not become a second event store or synchronization authority.

Keep the trust boundaries explicit: the installation bearer authenticates only the dedicated planned/due read route; it cannot authenticate a human, substitute for the Supervisor token, authorize historical events, or grant writes. Verify scope and digest before returning event data, use constant-time digest comparison, and avoid secrets and event content in diagnostics. A complete read is published only after all bounded pages succeed; failure must not leave a partial calendar presented as complete.

The selected project confirms the application query and projection files cited above. The proposed dedicated HTTP adapter, composition, and Core integration files are prospective creates named in the host-owned inventory; their existence or implementation is not asserted. Acceptance should exercise actual Core registration and config flow, same-source reconfiguration and rotation, access isolation through both compositions, event semantics, bounds and pending/unavailable behavior, retry, and unload in the disposable Core 2026.10.4 environment. The selected compatibility document records platform references, not these increment's acceptance.

## 9. UI/UX and content contract

The Core integration uses the native configuration and reconfiguration flows, Calendar view, event card, and unavailable presentation. Configuration accepts the Domus endpoint and masks the installation bearer; setup failures and wrong-source identity receive clear English and Spanish messages. The calendar entity represents one configured installation and channel. Show bounded status and the next event only; event details come from the bounded calendar read. Date-only events appear as one all-day event ending at the next date. A timed occurrence appears as a one-minute marker with an exclusive end. Preserve projected UIDs, ISO dates, and aware timestamps with their resolved offsets. An unavailable read must not appear as an empty calendar. These are proposed behaviors; the selected tree contains no native calendar integration files among the declared prospective paths.

## 10. Failure, recovery, and cleanup

Invalid, missing, expired, wrong-scope, or revoked bearer credentials, source timeouts, malformed pages, expired cursors, and range, page, or total-result exhaustion produce an unavailable read without presenting partial results as an empty calendar. A known event in a pending projection retains its pending state; an empty pending result for the requested range is unavailable. Normal one-minute polling retries a later failed read. Operators rotate or revoke access by replacing or removing the configured digest and restarting Domus, then reconfigure the existing Home Assistant entry with the replacement bearer. Reconfiguration must confirm the same source identity and retain the entity identity; a different source is rejected. Unload cancels scheduled polling and entry listeners. Do not include credentials or event content in diagnostics. The native entity lifecycle and these failure behaviors remain prospective in this increment.

## 11. Security, permissions, and privacy

The installation bearer is a randomly generated, calendar-only credential containing the Domus installation UUID and channel. Domus stores its SHA-256 digest in operator configuration; verify the bearer scope and digest using constant-time comparison. Permit reads only for planned and due calendar pages on the dedicated endpoint. Deny writes, missing or malformed credentials, duplicate configuration, wrong scope, old credentials, and unauthorized historical-event requests without revealing event data. Never substitute a human session or Supervisor token, and do not share credentials with the gateway. Require HTTPS for standalone access. On the Supervisor network, use a separate private unpublished listener and preserve the existing Ingress and human-session boundaries. The existing owner describes those boundaries and its broader HA security contract in `specs/home-assistant-surface.md`; native calendar access is a proposed addition.

## 12. Observability and operational UX

Expose only safe pending or unavailable state and error categories needed for recovery. Error messages and diagnostics must omit bearer values, event data, and complete URLs. Keep status bounded to availability and the next event; do not expose an unbounded event payload as entity state. No telemetry leaves the installation by default, consistent with the existing Home Assistant surface contract in `specs/home-assistant-surface.md`. The proposed calendar implementation and its operational evidence have not yet been observed in the selected tree.

## 13. Compatibility, migration, rollout, and rollback

Qualify Home Assistant Core 2026.10.4 in a disposable environment with both the standalone HTTPS connection and the private Supervisor-network composition. This version is pinned by the compatibility matrix in `docs/compatibility-home-assistant.md`, whose reference rows do not establish native-calendar acceptance. Later Core versions require separate qualification; do not impose a runtime version ceiling. No existing Domus application data migration is proposed. Opt-in digest configuration is disabled until an operator configures it; replacing or removing the digest and removing the Home Assistant entry disables this surface. No release, live installation, deployment, or promotion is authorized by this increment.

## 14. Testing strategy and numeric budget

The minimum is seven distinct cases, counted once each: two Core configuration cases cover registration, duplicate denial, bearer rotation, source identity and reconfiguration; two access isolation cases cover route scope, unchanged human and Ingress boundaries, denied writes, credential substitution and unauthorized history; one calendar semantics case covers event identity, all-day dates, offsets and interval overlap; and two read lifecycle cases cover bounds, malformed or pending reads, retry, availability and unload. This is a minimum risk budget, not evidence that the cases have run or that the inventory is semantically complete.

Keep the repository’s full global and changed-file coverage requirements. Exercise pure mapping and bounds with deterministic values, and test actual Core config flow, entity registration and unload in a disposable Core 2026.10.4 environment against both Domus compositions. Include negative security assertions and page-level failure assertions; a failed or exhausted read must not become an empty calendar. The selected CI workflow declares Python, Node, frontend, architecture, documentation and container checks, but does not establish execution of these proposed acceptance cases or Home Assistant Core acceptance.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Core configuration | 2 | Observable scenarios in the case inventory. |
| Access isolation | 2 | Observable scenarios in the case inventory. |
| Calendar semantics | 1 | Observable scenarios in the case inventory. |
| Read lifecycle | 2 | Observable scenarios in the case inventory. |
| Total | 7 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
| --- | --- | --- | --- |
| domus-native-calendar-C01 | Core configuration | domus-native-calendar-R1 | Actual Core config flow registers a read-only calendar and denies a duplicate source identity. |
| domus-native-calendar-C02 | Core configuration | domus-native-calendar-R1, domus-native-calendar-R2 | Rotation and reconfiguration keep entity identity, deny the old bearer and reject a different source. |
| domus-native-calendar-C03 | Access isolation | domus-native-calendar-R2 | Both Domus compositions allow the scoped bearer only on the dedicated planned/due route; verify unchanged Ingress and human routes. |
| domus-native-calendar-C04 | Calendar semantics | domus-native-calendar-R3 | Native event pages preserve UIDs, all-day dates and resolved offsets, including half-open overlap. |
| domus-native-calendar-C05 | Read lifecycle | domus-native-calendar-R4 | Range/page exhaustion, malformed pages and pending empty reads are unavailable; known pending events retain pending state. |
| domus-native-calendar-C06 | Read lifecycle | domus-native-calendar-R4 | Retrying after a source failure restores availability and unload stops scheduled polling. |
| domus-native-calendar-C07 | Access isolation | domus-native-calendar-R2 | Unsupported writes, human/Supervisor credential substitution, wrong scope and unauthorized historical event requests reveal no event data. |

## 15. Documentation and discoverability

Document operator opt-in and digest setup, standalone HTTPS and private Supervisor-network connection choices, duplicate handling, reconfiguration, rotation and revocation, and the meaning of pending and unavailable results. Explain calendar dates and timed markers in accessible terms, and provide recovery guidance for failed credentials, unavailable reads and unload/reload. The 25 declared inventory rows include the prospective companion specification, references to existing owner contracts, documentation changes, prospective implementation and test files, and repository CI evidence; each row remains the authoritative navigation declaration.

The existing calendar query and HA projection are in `backend/src/domus/application/calendar_queries.py` and `backend/src/domus/application/ha_calendar_projection.py`. The projection carries event UID, kind, start, all-day flag, task state, page cursor and pending status, and marks external synchronization disabled. The query uses a bounded `CalendarRange`; `backend/src/domus/domain/calendar_values.py` validates ranges from 1 through 366 days. These are existing selected-source facts, not evidence that the proposed Core integration or dedicated installation endpoint exists. The compatibility matrix in `docs/compatibility-home-assistant.md` records Core 2026.10.4 as a reference version and says other combinations remain unverified; it does not establish native-calendar acceptance.

| Path | Change |
| --- | --- |
| specs/home-assistant-calendar.md | create |
| specs/home-assistant-surface.md | reference |
| specs/recurrence-calendar.md | reference |
| specs/recurrence-lifecycle-calendar.md | reference |
| docs/compatibility-home-assistant.md | update |
| docs/tasks/calendar.md | update |
| docs/tasks/ha-calendar.md | create |
| backend/src/domus/application/calendar_queries.py | update |
| backend/src/domus/application/ha_calendar_projection.py | reference |
| backend/src/domus/entrypoints/ha_calendar_http.py | create |
| backend/src/domus/composition/ha_calendar.py | create |
| backend/src/domus/composition/ha_app.py | update |
| backend/src/domus/composition/ingress.py | update |
| backend/src/domus/composition/server.py | update |
| custom_components/domus_calendar/__init__.py | create |
| custom_components/domus_calendar/manifest.json | create |
| custom_components/domus_calendar/client.py | create |
| custom_components/domus_calendar/calendar.py | create |
| custom_components/domus_calendar/config_flow.py | create |
| custom_components/domus_calendar/translations/en.json | create |
| custom_components/domus_calendar/translations/es.json | create |
| tests/backend/test_ha_calendar_installation.py | create |
| tests/ha/calendar_smoke.py | create |
| tests/containers/test_app_image.py | update |
| .github/workflows/ci_check.yml | update |

[specs/home-assistant-calendar.md](home-assistant-calendar.md) · [specs/home-assistant-surface.md](home-assistant-surface.md) · [specs/recurrence-calendar.md](recurrence-calendar.md) · [specs/recurrence-lifecycle-calendar.md](recurrence-lifecycle-calendar.md) · [docs/compatibility-home-assistant.md](../docs/compatibility-home-assistant.md) · [docs/tasks/calendar.md](../docs/tasks/calendar.md) · [docs/tasks/ha-calendar.md](../docs/tasks/ha-calendar.md) · [backend/src/domus/application/calendar\_queries.py](../backend/src/domus/application/calendar_queries.py) · [backend/src/domus/application/ha\_calendar\_projection.py](../backend/src/domus/application/ha_calendar_projection.py) · [backend/src/domus/entrypoints/ha\_calendar\_http.py](../backend/src/domus/entrypoints/ha_calendar_http.py) · [backend/src/domus/composition/ha\_calendar.py](../backend/src/domus/composition/ha_calendar.py) · [backend/src/domus/composition/ha\_app.py](../backend/src/domus/composition/ha_app.py) · [backend/src/domus/composition/ingress.py](../backend/src/domus/composition/ingress.py) · [backend/src/domus/composition/server.py](../backend/src/domus/composition/server.py) · [custom\_components/domus\_calendar/\_\_init\_\_.py](../custom_components/domus_calendar/__init__.py) · [custom\_components/domus\_calendar/manifest.json](../custom_components/domus_calendar/manifest.json) · [custom\_components/domus\_calendar/client.py](../custom_components/domus_calendar/client.py) · [custom\_components/domus\_calendar/calendar.py](../custom_components/domus_calendar/calendar.py) · [custom\_components/domus\_calendar/config\_flow.py](../custom_components/domus_calendar/config_flow.py) · [custom\_components/domus\_calendar/translations/en.json](../custom_components/domus_calendar/translations/en.json) · [custom\_components/domus\_calendar/translations/es.json](../custom_components/domus_calendar/translations/es.json) · [tests/backend/test\_ha\_calendar\_installation.py](../tests/backend/test_ha_calendar_installation.py) · [tests/ha/calendar\_smoke.py](../tests/ha/calendar_smoke.py) · [tests/containers/test\_app\_image.py](../tests/containers/test_app_image.py) · [.github/workflows/ci\_check.yml](../.github/workflows/ci_check.yml)

## 16. Acceptance scenarios

Acceptance is the seven distinct section 14 scenarios, with observable state and side-effect assertions. In the actual Home Assistant Core config flow, a first read-only calendar entry registers for one installation and channel; a duplicate source identity is denied. Reconfiguring the same source with a rotated bearer preserves the entity identity, denies the old bearer, and rejects a different source.

Against both Domus compositions, the scoped installation bearer authorizes only the dedicated planned/due read path. Verify the existing Ingress and human routes retain their boundaries; unsupported writes, a human or Supervisor credential used in place of the installation bearer, wrong scope, and unauthorized historical event requests disclose no event data. Native event pages preserve projected UIDs, date-only all-day events, resolved timestamp offsets and half-open overlap.

Exhausted range, page or total-event bounds, expired cursors, malformed pages, and pending reads with no known intersecting events produce unavailable results rather than a false empty calendar. Known pending events retain pending status. A source failure recovers on normal retry, and unloading the entry stops scheduled polling and removes its listeners. Test Core 2026.10.4 in a disposable environment with standalone and private Supervisor-network compositions. The selected source already contains a calendar projection in `backend/src/domus/application/ha_calendar_projection.py`; prospective integration paths do not establish executed acceptance.

## 17. Requirements traceability

The requirement-to-case mapping is reciprocal with the seven section 14 inventory definitions. `domus-native-calendar-R1` is exercised by `domus-native-calendar-C01` and `domus-native-calendar-C02`, which verify registration, duplicate denial, stable source identity and reconfiguration. `domus-native-calendar-R2` is exercised by `domus-native-calendar-C02`, `domus-native-calendar-C03` and `domus-native-calendar-C07`, covering bearer rotation, route isolation, preserved human and Ingress boundaries, unsupported writes and credential-substitution denials. `domus-native-calendar-R3` is exercised by `domus-native-calendar-C04`, covering UID, all-day date, offset and overlap semantics. `domus-native-calendar-R4` is exercised by `domus-native-calendar-C05` and `domus-native-calendar-C06`, covering bounded reads, pending and unavailable distinctions, recovery retry and polling cleanup.

Publication requires the specification to satisfy the required format; internal and cross-document consistency to be checked; and reciprocal catalog ownership, paths and evidence to agree with the generated view. These are publication constraints, not product goals or executed acceptance. The selected tree declares `domus-check` as `domus_tooling.cli:main` in `pyproject.toml`, and `ci_check.yml` invokes `uv run --no-dev domus-check docs` for local documentation links. The inspected workflow definition does not establish that this command checks SDD format, cross-document consistency, catalog ownership or the generated view. A concrete invocation and prerequisite for those SDD/catalog checks remain unverified; passing a documentation-link check cannot substitute for those outcomes.

| Requirement | Cases |
|---|---|
| domus-native-calendar-R1 | domus-native-calendar-C01, domus-native-calendar-C02 |
| domus-native-calendar-R2 | domus-native-calendar-C02, domus-native-calendar-C03, domus-native-calendar-C07 |
| domus-native-calendar-R3 | domus-native-calendar-C04 |
| domus-native-calendar-R4 | domus-native-calendar-C05, domus-native-calendar-C06 |

## 18. Implementation sequence

Implement the dedicated, narrowly scoped planned/due calendar read path and wire it through both Domus compositions. Preserve the existing Ingress and human-session boundaries. Then build the Core integration’s config flow, client, read-only entity, reconfiguration behavior, and unload lifecycle. Validate actual Core registration, bounded reads, event mapping, access isolation, recovery, and cleanup against both compositions. Update operator documentation for setup, rotation, revocation, and pending or unavailable results. The prospective declarations identify 25 path operations; create rows remain proposed until implemented. Relevant existing contracts are `specs/home-assistant-surface.md`, `specs/recurrence-calendar.md`, and `specs/recurrence-lifecycle-calendar.md`. The selected compatibility reference is `docs/compatibility-home-assistant.md`; its pinned version does not establish calendar acceptance.

## 19. Definition of Done

The seven distinct acceptance cases are preserved in the case inventory and must pass, along with the repository’s complete global and changed-file coverage requirements. Verify Core 2026.10.4 in a disposable environment against both Domus compositions. Confirm that one read-only entity registers per installation and channel, duplicate source configuration is denied, and same-source reconfiguration preserves entity identity while rotation denies the prior bearer. Confirm the bearer is limited to the dedicated planned/due read path and that writes, wrong scope, human or Supervisor credential substitution, and unauthorized historical requests reveal no event data. Confirm event UIDs, all-day dates, resolved timestamp offsets, and half-open overlap; enforce the stated polling, range, page, and total-read bounds; report pending and unavailable results distinctly; recover on retry; and stop polling on unload.

Before publication, the specification satisfies the required format; internal and cross-document consistency is checked; and reciprocal catalog ownership, paths, and evidence agree with the generated view. These are observable publication outcomes, not proof of semantic completeness or executed acceptance. The selected source declarations and inspected definitions do not establish a concrete specification/catalog validation invocation; that invocation and any prerequisite remain unverified. Do not treat a declared command as execution or acceptance. CI, Copilot Verification, and Bugbot must have no unresolved findings on the exact commit before merge. No release, live installation, deployment, or promotion is authorized.

## 20. References and decisions

This is a companion to the retained owner `specs/home-assistant-surface.md` for the native calendar increment. Existing Home Assistant and recurrence contracts and cases remain in force; this companion defines only its seven new cases. Domus remains authoritative for projected event data. The issue fixes the compatibility exercise at Core 2026.10.4 in a disposable environment for both compositions; later versions require separate qualification, with no runtime version ceiling. Installation opt-in uses a random bearer containing the installation UUID and channel, with only its SHA-256 digest configured in Domus; rotation or revocation takes effect after changing or removing the digest and restarting Domus. The installed owner preview and historical test evidence do not establish acceptance of this increment. The compatibility matrix `docs/compatibility-home-assistant.md` records the pinned reference version without claiming native calendar acceptance.
