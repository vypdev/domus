# Installation and operation

Install Domus Edge from the reviewed Domus development repository, start it and select Open Web UI.
No password, copied token, OAuth callback or port configuration is needed. The first installation
builds the reviewed runtime from an immutable source commit and frozen dependencies; allow the build
to finish before opening the UI.

The preview shows whether the current human can be verified through Home Assistant. It creates no
household or business database. Native outage-grace sessions and the complete household UI remain
pending. Connection failure is reported without granting default administrator access.

The container requests Core API access to verify individual HA users. HA grants this technical
connection administrator privileges, which the app never treats as the human's permissions.
It requests no Supervisor management API, host port, host network, privileged capabilities, devices
or host-directory mounts. Runtime execution uses UID/GID 65532. Tokens remain process memory and
never appear in the web page, logs or business storage.

Stop the app to end the preview. This does not sign out your HA frontend. There is no Domus OAuth
grant to revoke for this native mode. Remove the development app/repository after its owned test;
do not migrate production household data into this preview. A stable package will be published
separately when its acceptance gates pass.
