# Installation and operation

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
[restoration guide](https://github.com/vypdev/domus/blob/feature/6-implement-home-assistant-identity-and-sqlite-platform-persistence/docs/restoration.md)
for the exact console commands. Restore is not available from the household entry interface.
App removal with data
deletion removes the app's private records; use deliberate operator backup procedures before removal.
Changing public_origins requires a restart. Edge.2, Edge.3 and Edge.4 are marked as breaking versions
so an unattended update cannot cross their configuration and schema/history boundaries. Edge.4
migrates existing verified schema 3/4 data to schema 7. Old Edge.2/3 images must refuse the new data
without changing it; they cannot be used directly as a downgrade. Recovery requires a compatible
image/data checkpoint pair. Preserve the original pre-upgrade data checkpoint for deliberate
rollback. A passing build is separate from actual upgrade, restore and owner adoption evidence.

The build fetches exact reviewed source, compiles with pinned Node/pnpm and includes the UI in the
installed Python wheel. Node and browser test controls are absent from the runtime image. The
interface uses the same private listener and accepted Ingress prefix; no extra port, credential,
Supervisor API permission or host mount is added. The candidate package is not a stable release.

Stopping does not sign out your HA frontend. There is no Domus OAuth
grant to revoke for this native mode. Remove the development app/repository after its owned test;
do not migrate production household data into this preview. A stable package will be published
separately when its acceptance gates pass.
