# Installation and operation

Install Domus Edge from the reviewed Domus development repository. In Configuration, set
public_origins to the URLs used to open HA, for example http://homeassistant.local:8123. Enter one to
four distinct origins without paths, credentials, queries or fragments, then start and select Open Web UI.
No password, copied token, OAuth callback or host port configuration is needed. The first installation
builds the reviewed runtime from an immutable source commit and frozen dependencies; allow the build
to finish before opening the UI.

The preview shows whether the current human can be verified through HA. It creates one private
installation identity and SQLite schema, retaining both across restart/update. It never implicitly
creates a household or member. The household/member/policy APIs and console-approved recovery are
included; the product UI is still a connection page. Existing sessions have bounded local read access
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
for the exact console commands. Restore is not available from the connection page.
App removal with data
deletion removes the app's private records; use deliberate operator backup procedures before removal.
Changing public_origins requires a restart. Edge.2 and Edge.3 are marked as breaking versions so an
unattended update cannot cross their configuration and schema/history boundaries. Schema 4 refuses
downgrade by Edge.2; recovery requires a compatible image/data checkpoint pair.

Stopping does not sign out your HA frontend. There is no Domus OAuth
grant to revoke for this native mode. Remove the development app/repository after its owned test;
do not migrate production household data into this preview. A stable package will be published
separately when its acceptance gates pass.
