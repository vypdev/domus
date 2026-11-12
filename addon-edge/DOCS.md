# Installation and operation

Edge 0.0.0-edge.30 packages the immutable runtime declared in
[artifact.json](artifact.json). Overview shows the signed-in member's completed tasks and
posted earned points for the current Family week. Open Family for the full report.
In Household settings, authorized members can preview a manual task proposal and
see whether an optional stock condition matches. Preview leaves tasks and stock unchanged.
If the product list fails to load, the title-only preview remains available and
the draft is preserved while reloading the list.
People with task configuration permission can set optional base points when creating a task.
Leaving the field empty uses the household default. Home Assistant can read
the due-today and overdue task counts shown on Overview through a dedicated installation
grant. Enable the [native deadline sensors](../docs/tasks/ha-deadline-sensors.md) using
the optional `ha_deadline_digest` setting. The calendar uses its own
`ha_calendar_digest` setting. Both share the private app port `8100` when enabled.
This preview retains SQLite schema 31. Edge.13 introduced that schema and is listed
in `breaking_versions`. Keep a compatible image and stopped-app backup before
upgrading from an earlier schema. A binary that expects the earlier schema
requires its compatible data backup.
A separate Supervisor repository source creates an independent app and data
directory. Check the source, installed version and app slug before using
a preview.


Install Domus Edge from the reviewed Domus development repository. In Configuration, set
public_origins to the URLs used to open HA, for example http://homeassistant.local:8123. Enter one to
four distinct origins without paths, credentials, queries or fragments, then start and select Open Web UI.
No password, copied token, OAuth callback or host port configuration is needed. The first installation
builds the reviewed runtime from an immutable source commit and frozen dependencies; allow the build
to finish before opening the UI.

The interface shows current verified household access in English or Spanish. It creates one private
installation identity and SQLite schema, retaining both across restart/update. It never implicitly
creates a household or member. The household/member/policy APIs and console-approved recovery are
included. Household setup and own membership require an explicit reviewed action; opening or
refreshing the page never creates either. The default setup maps current HA administrators to Domus
administrators. Pending membership does not grant household access. Original-request recovery reuses
the exact original key after fresh access checks; it never automatically repeats a command. Close
is available after the bounded in-flight command settles; it clears owned browser recovery data
and does not revoke HA sign-in. A stale close intent during a command is refused, not queued.
Existing sessions have bounded local read access
during HA outages; writes require fresh proof. Failure never grants default administrator access.

The container requests Core API access to verify individual HA users. HA grants this technical
connection administrator privileges, which the app never treats as the human's permissions.
It requests no Supervisor management API, host port, host network, privileged capabilities, devices
or host-directory mounts. A short container-root launcher prepares only /data/domus and then clears
supplementary groups and executes the server as UID/GID 65532. Existing data must already have the
correct private ownership/mode; there is no recursive repair or root server fallback. Domus reads the Supervisor-provided
credential into private runtime memory and does not write it into its web page, logs or business
storage. HA/Supervisor owns provisioning and the credential's platform lifecycle.

Stop the app to close its local sessions and release storage locks. Household records and original
operation receipts remain in /data/domus. Do not remove the installation marker, copy SQLite alone
or share this data with Stable. Edge.3 includes console-only restoration to a new verified generation;
it preserves later operation evidence without reapplying rolled-away effects. Stop the app before
restore preparation/activation. Inspect and resume the same activation ID after an uncertain result.
The retained source-checkpoint supports deliberate rollback reconciled against the latest history.
Do not switch root pointers or run an older image manually. See the
[restoration guide](https://github.com/vypdev/domus/blob/93d7d77b98a196640bf0049bca36a3d90b7a5857/docs/restoration.md)
for the exact console commands. Restore is not available from the household entry interface.
App removal with data
deletion removes the app's private records; use deliberate operator backup procedures before removal.
Changing public_origins requires a restart. Edge.2, Edge.3 and Edge.4 are marked as breaking versions
so an unattended update cannot cross their configuration and schema/history boundaries. Edge.4
migrates existing verified schema 3/4 data to schema 7. Old Edge.2/3 images must refuse the new data
without changing it; they cannot be used directly as a downgrade. Recovery requires a compatible
image/data checkpoint pair. Preserve the original pre-upgrade data checkpoint for deliberate
rollback. A passing build is separate from actual upgrade, restore and owner adoption evidence.
Edge.5 keeps schema 7 and supports the same owned Edge.4 data without a schema transition. It
localizes the technical state as well as the main heading. Its reviewed immutable source is a new
build; the previously published Edge.4 source pin is not changed.

Edge.6 adds the household administration workspace and upgrades supported owned data to schema 9.
An authorized participant can inspect permitted roster facts, review household/member/access-policy
changes and manage their own private preferences. An optional alias changes presentation while the
canonical HA account remains the identity. Each form preserves its independent original revision.
A changed or missing verified household clears private drafts, including detached confirmation controls.
Opening, translating or refreshing a view sends no household mutation.

Edge.6 is listed in breaking_versions because it crosses the schema-9 boundary. Home Assistant
requires attention before automatic updates install or cross a listed version; see its
[app configuration reference](https://contributors.home-assistant.io/apps/reference/configuration/).
Preserve a complete owned pre-upgrade checkpoint, installation marker and operation history.
Restoring an earlier household state uses the schema-9 console workflow with the compatible runtime,
retaining later original-operation evidence. A verified compatible application/data pair supports
binary rollback. Old Edge.5 and earlier images refuse schema 9 without changing its files; choosing
an earlier household snapshot does not make a schema-9 generation readable by those images.

The Edge.9 artifact declaration fixed the reviewed source/archive and all 151 Python/four UI
file fingerprints. Application CI builds the actual pinned installer image on amd64 and aarch64,
checks those bytes, exercises its native restart/authority boundary and standalone UI, and runs
the installed Edge.5 upgrade/replay/restore cycle. The separate current-source image retains its
complete household administration and task browser campaign. These fixtures use isolated owned data; actual owner
adoption and required human UX are additional acceptance steps.

Edge.7 retains the Edge.6 runtime/schema and declares `backup: cold`. Supervisor stops Domus while
copying its private data, causing a brief interruption. In-memory sessions close; after restart,
reopening the interface verifies the current HA identity. No backup hooks or data exclusions apply.
See the [Supervisor backup policy](https://contributors.home-assistant.io/apps/reference/configuration/#backups).
For an older preview without this declaration, explicitly stop it before a pre-update app backup,
verify the stopped state and backup completion, and restart only if it was running beforehand.
A readable archive/hash alone does not prove a consistent SQLite capture during concurrent writes.
An app backup also does not preserve later operations by itself; use the console restoration protocol
when reconciling newer original-operation evidence. Never replace a live data directory manually.

The build fetches exact reviewed source, compiles with pinned Node/pnpm and includes the UI in the
installed Python wheel. Node and browser test controls are absent from the runtime image. The
interface uses the same private listener and accepted Ingress prefix; no extra port, credential,
Supervisor API permission or host mount is added. The candidate package is not a stable release.

Stopping does not sign out your HA frontend. There is no Domus OAuth
grant to revoke for this native mode. Remove the development app/repository after its owned test;
do not migrate production household data into this preview. A stable package will be published
separately when its acceptance gates pass.


Edge.8 makes Tasks the default screen. Create a task with a title, optional description and priority;
open it to claim and mark your own work done. Current authorized reviewers can approve/reject the
current cycle or reopen it with a reason. Linked material quantities respect their unit precision;
a recorded completion never fabricates stock or downstream point delivery. Uncertain requests
remain inspectable by their original key without automatically sending another command. Technical
identifiers are under optional details. Household settings remain in the Household tab.

This increment keeps schema 9 and the existing installation options. It adds no breaking-version
boundary, host exposure or Core API permission. The immutable artifact fixes the published runtime;
both CPU jobs exercise all 44 household/task browser journeys in the current-source image. The
calendar, full recurrence editors, points/rewards and supplies screens are still being developed.
Actual owner installation and usability review are separate from isolated browser fixtures.


Edge.9 corrects task-specific original recovery so it checks current task-read and the recorded
command grants without requiring operations.read for general browsing. The general operation-by-ID
query keeps that separate permission. Form-level title, description and reason limits count Unicode
code points, retain invalid input with a visible error and prevent submission until corrected. Both
deployments exercise restricted lost-response recovery and exact astral-character bounds. This is
a distinct immutable preview from Edge.8; it retains the same schema and permission scope.
