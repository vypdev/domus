# Household entry interface foundation

The development branch implements pure entry/setup decisions, the bounded request journal with
its owned sessionStorage adapter, the generation-fenced entry controller, browser capability and
lifecycle composition, an owned English/Spanish Lit view, the product module entrypoint and
same-listener built UI delivery. Strict frontend HTTP adapters attach and
decode the server context contract. Both server compositions
now expose verified session context and enforce supplied context assertions before protected work.
Edge.4 packages the original interface; its separate owner installation has passed the Ingress identity
and English/Spanish opening checks below. The technical-status correction is in the distinct Edge.5
candidate. The retained Edge.3 application is unchanged.

The [entry specification](../specs/household-entry-interface.md) retains eight requirements and 48
planned acceptance cases. The first model tests exercise membership decisions, explicit setup
defaults, input bounds and truthful unavailable facts; they do not complete browser journeys.

## Decisions and setup

The model consumes decoded server facts and never infers a grant from a profile name. Setup and
enrollment controls require the server's corresponding flag and a full, unexpired session. Pending
membership offers refresh; suspended or archived membership asks an administrator to review the
existing linkage. Those states never offer replacement self-enrollment.

Read-only grace retains the membership state and disables setup and enrollment. Household facts
are displayable only for active membership with the actual household.read grant. The server checks
each request independently. A model decision never extends the original deadline. Missing, expired
or inconsistent proof selects native HA reopening or the existing standalone sign-in path. Missing
data and preview without household APIs remain unavailable.

Setup takes only name and timezone. It selects all_ha_administrators, expected revision zero, and
no actor or selected account. Names are bounded to 160 Unicode code points before trimming; timezones
to 128. Blank, Unicode-control (C0, DEL and C1) and unpaired-surrogate input receives a field error without changing
the caller's draft. The server owns final authorization, uniqueness and timezone-catalog validation.
These checks do not authenticate or send a command.

## Original requests and local recovery

The version-1 journal holds up to eight requests in at most 64 KiB of canonical UTF-8 JSON. Setup
and own enrollment have exact allowed fields; transport credentials, raw errors and arbitrary actions
are rejected. The original key, payload, creation time and one-hour deadline remain immutable across
reload, uncertain outcomes and committed/historical results. Validation never normalizes a stored
payload. Known operation IDs cannot change or be replaced with an uncertain/rejected outcome.

Fresh server context binds one installation, Stable/Edge channel and verified subject. Opening may
establish an empty owned local journal after current-state reads; this writes no household/member
record. A known different context removes incompatible local requests before use. Invalid/future
versions, malformed or noncanonical JSON, duplicate keys, future timestamps and clock regression
block use. Updating the observation time never extends an original deadline. Expired records may
be pruned; unresolved unexpired work is never silently evicted. Resolved requests can be dismissed.

The adapter touches only domus.entry.journal.v1. Every update compares the prior serialized value,
writes and confirms readback. Failure, external change or disappearance invalidates the opened
handle. A controller must obtain fresh server context/state before reopening and must persist a
prepared request before any send. The journal cannot grant access or prove current membership.

Involuntary session loss detaches memory and retains local recovery evidence. Explicit logout clears
memory first and removes/verifies only the owned key. Failed cleanup is reported as uncertain; it
never restores authority. A storage failure after receiving a server receipt does not negate that
receipt or justify a new request key. Adapter tests use simulated receipts plus actual isolated
Chromium sessionStorage, without contacting the owner's HA.

## Entry controller

Opening and refreshing read session, current authorization and permitted household facts. They
create no household or membership. Semantic server ports must bind each read and command to the
expected installation/channel/subject, reject a mismatch, and return strictly decoded immutable
facts. Expected context is an assertion, never an actor selector. Both server compositions now reject
supplied mismatched assertions; the frontend HTTP adapter attaches and validates that contract.
Domain and Application import no browser, storage, transport or framework API.

Setup, enrollment, original-request recovery and resolved-request dismissal obtain fresh session
and current state. Setup uses the explicit validated default mapping. Recovery is separate from
eligibility for a new effect: pending enrollment may check its original request; setup recovery
requires current setup permission or an active household-management grant. The server independently
enforces current original-command authority and idempotency. Rejection, missing proof, grace,
suspended/archived linkage and incompatible context never become a cached grant.

One command is allowed in flight, including its preflight and receipt reconciliation. A new key is
not generated while unexpired prepared/uncertain work exists. Prepare must persist and read back
before send. No opening, refresh, receipt, timeout or transport failure automatically resubmits.
Deliberate recovery reuses the exact original key/payload, creation/deadline and known operation
identity; changes observed during fresh reads fail closed. Dismissal cannot evict unresolved work.
Logout is also blocked by the command's synchronous in-flight guard, including preflight, sending
and reconciliation. A stale enabled DOM control cannot erase the prepared record or stop runtime
timers while the result is pending. Once the bounded command settles, deliberate logout resumes
its normal cleanup/revocation behavior. Closing or unloading the page still hides memory and
preserves the original recovery evidence.

Every replacement view cancels owned reads and fences all late results, including rejected reads,
sent responses and logout callbacks. Cancellation never claims to undo a command. Involuntary loss
or teardown detaches memory and preserves local recovery evidence. Tick uses the semantic anchored
clock; it never renews a session. Tick hides expired recovery records and completed results; a fresh
verified opening prunes expired stored records. A receipt arriving after session expiry remains
evidence of the earlier effect but cannot expose expired authority. Explicit standalone logout attempts actual logout even
if owned storage clearing fails. Native logout clears owned presentation/data and explains that HA
owns sign-out; it never invokes standalone revocation. Cleanup/revocation uncertainty stays explicit.

The controller tests use real Chromium and semantic server fakes, including one processed effect
whose first response is lost and then recovered after controller/storage-adapter recreation. These
are Application tests, not real HTTP/SQLite, rendered journeys, owner HA or package acceptance.

## Server context contract

The actual authenticated session response contains context with installation_id, channel,
deployment, application_base, household_api_available, server_time and expires_at. Native derives
the base from the accepted Supervisor prefix; standalone always uses the root. Forwarded prefixes
cannot replace either. UTC epoch milliseconds are anchored once to the monotonic lease clock;
later wall-clock changes and fresh/grace reads cannot extend the original session deadline.

Bound UI requests must supply X-Domus-Context as v1:installation:channel:subject, using verified
metadata and the verified HA user ID. The server compares this assertion with its real composition
and session before protected reads/CSRF/commands. Wrong or ambiguous assertions receive a safe
rejection without revealing expected context or creating a household. The assertion grants no role
and selects no actor. Legacy raw API requests may omit it; the frontend adapter always
send it on bound requests. Existing cookie/Ingress, Origin, CSRF and per-command current authority
remain mandatory. No CORS permission or public port is added.

Thirty-three additional backend scenarios exercise actual guarded ASGI/SQLite and both compositions,
including metadata, preview, stale context, role denial, original-key replay and fixed clock anchor.
These server tests do not wire the frontend adapter or prove rendered/owner acceptance. The checked
OpenAPI snapshots come from the actual applications. The host launcher test prepares its simulated
parent group explicitly so BSD group inheritance does not invalidate the fixture; production
ownership rejection and the original no-change assertions remain intact.
The lower-level legacy native factory can omit deployment metadata and returns context=null; it
rejects supplied context assertions. The product compositions always provide metadata. A missing
context must remain unavailable to the frontend, with no inferred installation or command grant.

## Frontend HTTP boundary

Composition supplies the current page's canonical origin and accepted deployment/base. The adapter
uses fixed relative paths, same-origin mode/credentials, no-store and no-referrer requests. It
rejects redirects, foreign response URLs, opaque responses and unsupported personal-response MIME
or caching. Bound reads, operation queries and commands carry exactly one verified context assertion.
No host message, query hint or API body selects an endpoint or actor.

Each logical operation has one 15-second deadline across its requests and streamed decoding. Abort
both cancels owned I/O and settles the caller independently of provider cooperation; late preflight
continuations cannot send another request. Body readers/listeners/timers are released. Native fetch
is invoked as a function, avoiding Chromium's observed Illegal invocation under a foreign receiver.
The native-fetch regression contacts only the isolated Vitest server; its missing product API is
correctly unavailable.

Responses are bounded to 64 KiB of streamed UTF-8, with fatal decoding, a sixteen-container limit,
duplicate decoded-key rejection and safe integer numeric lexemes. Fractional/exponent/negative-zero
wire encodings are unsupported by this integer-only entry contract. The key scanner uses one forward
pass, including malformed strings. Strict DTOs validate flags, scoped permissions, own linkage,
original receipts and actual delivery; no profile label invents a grant. Provider guidance is bounded
and discarded. Existing household DEL/C1 values remain readable as data; new setup keeps its stronger
validation and the exact original submitted payload remains unchanged.

Setup/enrollment get actual CSRF per call and preserve the original key/payload. Browser fetch supplies
Origin; the adapter never sets it manually. A valid bounded 401/403/409/422/503 error after POST is a
known rejection. Lost, malformed or unexpected POST results stay uncertain. Preflight failure sends
no mutation. No retry, key replacement or lease renewal is automatic. Standalone logout verifies the
current session/context, gets CSRF and attempts real logout; native refuses standalone revocation.
Operation reads retain the original ID/result and actual pending/delivered/suppressed state.

Recorded nonsecret wire from actual guarded native/standalone ASGI/SQLite providers is consumed by
Chromium tests. Two backend cases keep its structure current while allowing bounded guidance copy
edits. The controller/HTTP/journal composition also checks one simulated effect across a lost response
and deliberate same-key recovery. Production imports of test/story fixtures are rejected, including
type-only imports. These boundary/conformance tests are distinct from the built-product journeys,
rendered UI, HA observation and package acceptance recorded below.

## Browser composition and presentation

The server-anchored clock advances by monotonic elapsed time, rounds to integer milliseconds and
cannot rewind after fresh proof. Invalid samples, regression, provider failure and overflow fail
closed for the page. Web Crypto supplies exactly 128 random bits per request key; there is no weak
random or timestamp fallback. Navigation has only fixed same-origin sign-in/reopen destinations;
native never starts standalone OAuth.

The runtime composes these adapters with the actual controller, HTTP and journal. It publishes
loading/current views, schedules the nearest session/request deadline with bounded intermediate
ticks, and rechecks expiry on visibility changes without automatically refreshing authority. Exit
retires owned reads, timers, listeners and presentation. A persisted pagehide retains original tab
recovery data but closes access; persisted pageshow creates a fresh controller and obtains proof
again without sending the retained command. Timer epochs and controller generations fence late
callbacks, including a command response from before restoration. Explicit logout stops the local
lifecycle before upstream confirmation. Renderer/cancellation failures cannot restore authority.

The Lit view emits semantic intents only. It renders actual setup/join/membership/denied/unavailable,
grace, receipt and original-request states. Drafts survive refresh/language changes, errors have
associated descriptions and focus, storage failure visibly blocks new writes, and closed views
retain reentry even when a retired command is still pending. Household text stays inert; raw result
blobs, request keys/payloads, human/installation IDs and private Ingress data are not displayed.
English and Spanish have stable complete keys, with English fallback for unsupported language or
missing localized keys. Deadlines are explicitly UTC. The current design uses owned components,
system fonts and light/dark CSS with reduced-motion support.

Private drafts survive ordinary refresh within the same verified context but are retired before
rendering another installation/channel/account or a closed view. Live value binding also clears an
already edited DOM input when identity changes before Lit has committed the input event's update.

The built Storybook catalog contains fourteen fictional states and has no server connection. Its
eighteen Playwright cases cover the full English/Spanish by native/standalone display matrix,
actual keyboard submission and draft retention, error focus, and 360-pixel light/dark layouts with
measured primary-button contrast and rapid-edit account isolation. These are built component-catalog journeys, not product backend
or owner HA acceptance. Four representative original screenshots are retained with the evidence.
The dedicated every-PR frontend job builds/exercises this catalog and retains its outputs separately
from application coverage; production imports from stories/configuration are rejected.

Runtime/application typechecking remains strict with dependency declarations checked. As in the
existing framework fixture, the separate catalog typecheck skips dependency declaration checking:
the locked Storybook web-components package has an unused expected-error directive and incompatible
generic declaration under TypeScript 6. The original failure is retained. Authored story/configuration
code remains strict, real build/browser checks run, and no dependency source was patched.

## Product document and packaged resources

The Vite product build writes four generated resources under the backend package's ui directory:
the fixed document, its manifest and external JavaScript/CSS. Hatch includes those exact resources
in the Python wheel. They are generated artifacts, excluded from source control. A source checkout
without a product build returns an explicit unavailable page; it does not present an empty home.
An existing corrupt bundle fails startup. The loader snapshots a bounded, closed manifest/resource
graph and rejects symlinks, unknown files, inline executables and undeclared resources. Requests
read immutable bytes instead of resolving user-controlled filesystem paths.
The required CI job builds the wheel, compares every packaged UI resource with the actual build,
loads the extracted snapshot and rejects inclusion of browser test controls.

The nonpersonal root document and assets require the existing native source/session binding; they
do not convert that binding into verified human access. A temporary HA outage can still load the
interface. Standalone serves the nonpersonal document before sign-in. Personal API calls separately
require current proof, context assertions and their existing command authorization. These document
routes are excluded from personal API schemas. Standalone OAuth now returns to the fixed root,
removing callback parameters before the interface independently reads current session facts.
Unknown, revoked or mismatched human proof still receives 401 from session, authorization, household
and CSRF APIs. Source-bound static delivery neither calls the HA directory nor creates a lease/grant.
The rendered native product shows verification/reopening guidance without personal facts or setup
controls. This distinction is covered by three composed identity-denial regressions and a real
built-product browser journey. The contrary Bugbot suggestion is reported in
[Copilot #847](https://github.com/vypdev/copilot/issues/847); native finding resolution remains separate.

The inert version-1 JSON bootstrap contains exactly version, deployment, application_base and
style_nonce. The browser verifies it against its actual canonical location and derives origin only
from that location. It carries no identity, installation, role, token or command grant. The public
per-document style nonce permits Lit's style-element fallback under CSP; it is not authentication.
Successful documents allow only same-origin scripts, connections and assets and nonce-bound styles.
Neither unsafe-inline nor unsafe-eval is enabled. Native framing is same-origin; standalone framing
is denied. API, asset and error responses keep the default restrictive policy and no-store headers.

The DOM composition owns one mount, its semantic events, timers and reads. Malformed bootstrap,
unavailable browser capabilities and scheduling failures produce bounded guidance and explicit
reload. Replacing or detaching the owned element releases its resources. The actual module performs
no setup or enrollment automatically and never inspects HA's parent document or private storage.

Forty-five Playwright cases exercise the built product against both real Python compositions and
SQLite, wrapped by fictional loopback HA/Supervisor providers. They prove explicit keyboard setup,
inert household text, exact original-key recovery after a committed response is lost, unchanged
receipt/audit/outbox counts, blocked writes on silent storage failure, logout versus native close,
pending own enrollment, account-draft retirement, original-deadline read-only grace and Spanish
360px operation with actual CSP style fallback. A failed module download leaves visible reload
guidance without claiming an empty home. The standalone authorization fixture performs the
real state/browser-binding/PKCE callback flow with fictional one-use grants. Test controls are only
in tests/browser; they are absent from the application wheel.

The fixture now uses actual private owned installations. Its test-only operator invokes the real
installation console to create a baseline snapshot, stop the runtime, prepare and activate restoration,
and reopen the selected generation. Deliberate recovery then displays the historical original receipt
without recreating a household or changing the original request identity, payload or deadline.
Fresh Edge/Stable installations retire incompatible local records without replay. These tests exercise
channel binding, not distribution of a Stable image.

Independent browser contexts race setup only after both fresh preflights. Exactly one household,
member, receipt, audit record and outbox record is committed. A second binding for the same mapped
account gets a conflict; a different unlinked HA administrator is denied without implicit membership.
Failed owned-key removal closes local access while retaining original evidence and unrelated keys;
standalone still revokes its grant. Actual missing cookies and forged CSRF are rejected before effects.
Chromium owns Origin, so that attack uses a raw intercepted request to the real server and delivers
its actual denial. A virtual browser-clock wake proves local expiry and refusal to renew; it does not
advance the server clock. Independent backend tests cover server lease expiry.
Closing the actual browser tab preserves server receipts; a new tab has an empty local journal,
reads the same persisted household and original operation, and sends no automatic command.
Technical status values use the same English/Spanish catalog as the state heading. Both deployments
exercise the expanded details in each locale without losing the setup draft or changing permissions.

The provider-error regression captures the first exception once. A controlled typed provider-detail
leak passed the old get/set assertions but fails both corrected assertions; the production adapter
was restored byte-for-byte after each control. The alleged missing Lit await was already present and
the unchanged original test passed. Its awaits are now on separate lines with explicit closed-DOM
assertions. That false positive is reported in [Copilot #848](https://github.com/vypdev/copilot/issues/848).

## Owner Ingress observation

With explicit owner approval, Edge.4 was installed as a separate experimental app from this managed
branch. Only the authorized local public origin was configured; the previous stopped Edge.3 instance
and its data were retained. The new app started and its interface loaded inside HA's actual iframe.
The current HA account was verified without a separate login. English/Spanish switching and an
explicit status refresh both returned the unconfigured-household screen with current verified access.
No household was created. The initial wrapper remained on its loading screen until an active-tab
reload; the cause was not established. After reload the document, JavaScript, CSS, session and
authorization requests succeeded and the interface rendered. Private screenshots are retained locally,
not uploaded. This observation proves opening and identity, not the remaining owner business journeys.

## Development checks

From the root, using the locked Node and pnpm versions:

```sh
pnpm install --frozen-lockfile
pnpm --filter @domus/frontend exec playwright install chromium
pnpm check:frontend
pnpm test:frontend
pnpm build:frontend
pnpm test:frontend-entry
pnpm build:frontend-catalog
pnpm test:frontend-catalog
pnpm test
```

Application Vitest tests run in real headless Chromium with V8 measurement. All authored runtime,
including unimported modules, must reach 100% statements, branches, functions and lines globally and
per file. A separate filesystem inventory audits the summary. The fictional framework fixture and
Node policies retain their own measurements and artifacts. Application CI is a required CI Check
job on every PR update, including drafts and documentation-only changes.

The actual application import graph is checked alongside existing negative architecture fixtures.
Domain/Application remain independent of concrete adapters and frameworks. This initial model has
no DOM, storage, HTTP or framework dependency. See [development](development.md) for the other gates.
Model execution is separate from rendering, accessibility, integration, package and owner HA acceptance.

## Entry acceptance inventory

This maps each original household-entry-interface case to concrete executed proof. The 577 Chromium
unit/component executions, 45 product journeys and 18 catalog journeys are separate counts, not
replacement case IDs. Backend and image proof retain their own source identities. The corrected UI
has a new immutable Edge.5 pin and still needs actual image execution and final current-head gates
before this increment merges.

| Original case | Executed proof |
|---|---|
| C01 | Domain membership matrix, strict HTTP DTOs and rendered component/catalog membership states; profile labels never grant access. |
| C02 | Bootstrap/context negatives, actual native/standalone session metadata and context assertions. |
| C03 | Pure setup validation, explicit controller submission and actual product setup with the default mapping only. |
| C04 | Invalid input/draft/focus tests, Unicode regressions and actual backend timezone validation. |
| C05 | Strict journal shape/version/action/original-field and canonical decoding negatives. |
| C06 | Original deadline/backward-clock tests, expired command refusal and virtual browser wake. |
| C07 | Immutable key/payload/revision/time/operation tests and actual same-key product recovery. |
| C08 | Missing facts/preview/grace decisions and distinct unavailable rendered states. |
| C09 | Both actual product openings/refreshes are read-only; standalone sign-in and explicit setup/enrollment journeys. |
| C10 | Pending controller recovery and actual pending enrollment with no replacement linkage. |
| C11 | Controller preflight/send/reconciliation races, synchronous logout guard and one original request. |
| C12 | Actual committed-response loss/reload/recovery in both compositions; unchanged SQLite effect counts. |
| C13 | Controller current-denial/suspension tests, real server authority guards and composed rejected-human product journey. |
| C14 | Typed conflict/denial handling retains original request and draft without automatic rebase. |
| C15 | Real composed HA outage, backend expiry and browser local-deadline wake; no automatic lease renewal. |
| C16 | Late read/command/logout and context-replacement generation fences in real Chromium. |
| C17 | Actual standalone reauthentication after restoration retains deliberate original-key recovery. |
| C18 | Actual standalone state/binding/PKCE callback and revocation; native existing-session/close behavior. |
| C19 | Built native document/assets/API under the accepted prefix; wrong binding and prefix negatives. |
| C20 | Built standalone root/reload and fixed-root OAuth return, wheel and actual same-listener image probe. |
| C21 | Strict streamed UTF-8/JSON/MIME/status/size/deadline decoding and missing module/API guidance. |
| C22 | Actual cookie loss, forged CSRF and raw forged Origin reject before effects in both compositions. |
| C23 | Foreign endpoint/redirect/host-hint negatives and fixed navigation destinations. |
| C24 | Silent/throwing storage/readback/entropy failures prevent sending and preserve draft or original evidence. |
| C25 | Exact eight-record and 64-KiB journal boundaries, no unresolved eviction and UTF-8 size negatives. |
| C26 | Real Vite build, exact wheel resources and actual CPU image same-listener probes; inner-layer graph checks. |
| C27 | All 15 runtime modules, including unimported files, pass all four coverage metrics at 100%; independent filesystem audit. |
| C28 | Existing coverage negatives reject unimported/uncovered runtime and incomplete supported metrics. |
| C29 | Actual import/cycle/private-host graph checks and negative fixtures; production test/story imports rejected. |
| C30 | Every-PR CI contract tests and observed required jobs; no draft or documentation path bypass. |
| C31 | Fresh built Storybook: 14 states across both locales/deployments, 18 separate journeys. |
| C32 | Built product with both actual owned Python/SQLite compositions in Chromium; original build/browser/coverage outputs retained. |
| C33 | 360-pixel real product/catalog layouts and both-locale component bounds without horizontal overflow. |
| C34 | Actual keyboard setup/submission, associated accessible errors, focused invalid fields and named controls. |
| C35 | Distinct loading, denied, unavailable, grace and current states in component/catalog/product proof. |
| C36 | Complete locale/fallback keys, measured light/dark primary contrast, reduced-motion preferences and textual status. |
| C37 | Actual hostile household text remains inert; no script/image execution, unsafe endpoint or command interpretation. |
| C38 | Rendered default-mapping explanation, explicit setup consequence and no alternate-selector facade. |
| C39 | Suspended/archived model/component/catalog guidance and backend unique linkage/current-authority guards. |
| C40 | Actual decoded permissions, denied-read controller behavior and inert explicit technical permission identifiers. |
| C41 | Actual fresh Edge/Stable installation binding and account replacement retire incompatible journal/drafts without replay. |
| C42 | Actual owned-only close/revocation and failed-clear journeys, preserving server records and unrelated keys. |
| C43 | Real backend wrong-source/Origin/context and malformed header boundaries; no header-selected actor or role. |
| C44 | Real console snapshot/restore/restart returns a historical original receipt without recreating its absent effect. |
| C45 | Bundle/bootstrap/DOM/journal negatives exclude credentials/private facts; first-error leak control verifies bounded adapter errors. |
| C46 | Actual reload, cookie loss, local expiry and tab closure retain original server receipts and uniqueness guards. |
| C47 | Independent contexts race after fresh preflight: one home; mapped same-account conflict or unlinked-account denial. |
| C48 | Runtime/page teardown releases reads/timers/events, explicit browser-context cleanup and actual owned fixture lifecycle. |

The native owner observation above is additional bounded evidence. It does not replace this matrix
or claim completion of the other domain screens, Stable distribution or the all-domain release.
The owner's explicit exception permits reported Copilot infrastructure/context failures alongside
progress and merge; product findings still require resolution and full product coverage remains mandatory.

## Remaining delivery

The Edge.5 candidate pins corrected runtime source 271a3a0 and its verified source archive. Its separate
Node/pnpm build stage includes the exact UI in the noneditable Python installation and leaves
build tools out of the final image. Real amd64/aarch64 image execution, including UI resource bytes,
same-listener delivery, actual Edge.2/3 data upgrades, restore and downgrade refusal, remains an
independent CI gate. The frozen legacy builder is the byte-identical published Edge.3 recipe;
old-image tests cannot accidentally build new source or depend on the new frontend build stage.

Both actual CPU images have passed nineteen image/upgrade cases, and the owner opening/identity
observation is recorded separately. Complete accessibility/lifecycle acceptance and remaining owner
journeys still require their own evidence. Source/policy tests do not replace that acceptance or a
current-head review. Reported Copilot infrastructure failures are separate from product findings and
the required full test coverage. The all-domain first release,
both targets and isolated channels remain
required. Follow the existing [identity](identity-household.md) and [setup](household-setup.md) contracts.
