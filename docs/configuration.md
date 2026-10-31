# Authentication checkpoint configuration

For the native HA app, follow [app installation](installation-home-assistant.md). It uses Ingress
and requires no second login. The [native persistent development runtime](native-household-api.md)
also has an explicit database/UUID/fixed-origin development contract. Installed Edge.2 uses the
managed-directory launcher described below.
The options below apply to the independent standalone runtime.

Both CLIs support [--data-directory](owned-data-directory.md) for an existing private
0700 directory owned by its runtime UID. It generates/preserves installation identity, checks files
and holds the process lock until shutdown. Use it with --public-origin; do not also supply
--database or --instance-id. Installed Edge.2 wires this lifecycle through its fixed launcher.
Both explicit-file runtime modes reject a parent installation.json marker before SQLite initialization.
Use the owned-directory entrypoint for managed data; an explicit file cannot bypass its locks.

[domus-admin recovery approve](administrator-recovery.md) uses --data-directory and --channel to
attach to ready managed data in either mode, or --database plus --instance-id and --channel for an explicit standalone
file. It does not create/migrate storage and needs no HA token. New approval requires real terminal
input/output and the exact displayed request/target confirmation. HTTP cannot supply console authority.

[domus-admin snapshot](snapshots.md) provides explicit create/inspect operations. Creation uses the
same source selection as approval and requires a new private destination. Inspection instead requires
only --instance-id and --channel, without an active --database/--data-directory. Its --timeout defaults
to 30 seconds and accepts finite positive values up to 3600. It does not add a schedule or retention.

Status: these options run the standalone API. `--data-directory` or `--database` additionally wires the
persistent [household API](household-api.md); omitting both keeps the authentication preview. This is not a deployment
package or complete M1 acceptance. Both installation modes and Stable/Edge
remain first-release requirements. Production channels/artifacts have not been published.

| Option | Required/default | Contract |
|---|---|---|
| --ha-url | Required | One fixed HTTP(S) origin; no userinfo, query, fragment, arbitrary path or request override |
| --public-origin | Required | Exact Domus website/client/callback origin; HTTPS except explicitly enabled loopback development |
| --instance-id | Required without --data-directory; forbidden with it | Canonical nonzero UUID supplied by the installation for preview/explicit files; managed data generates it only on a valid empty start |
| --channel | Required | stable or edge; keep installation IDs, data, credentials and endpoint bindings separate |
| --development-http | Disabled | Permits a loopback public HTTP origin; development listener must bind loopback |
| --host | 127.0.0.1 | Listener binding; development accepts only 127.0.0.1 or ::1 |
| --port | 8099 | Integer 1–65535; no fallback to a different port or origin |
| --database | Omitted: authentication preview | Owned SQLite file with an existing parent directory; validates the configured UUID/channel and keeps state across restart |
| --data-directory | Omitted; mutually exclusive with --database | Existing runtime-owned 0700 directory; automatically preserves UUID/channel and holds runtime/maintenance guards until shutdown |

Example using the nonsecret UUID fixture from the tests; use the installation's own persistent UUID
for an actual installation:

```sh
uv run --frozen domus-server \
  --ha-url http://homeassistant.local:8123 \
  --public-origin http://127.0.0.1:8099 \
  --instance-id 047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6 \
  --channel edge \
  --development-http
```

The example omits both storage selections and opens no business database. With either selection, schema initialization
still creates no household or member: explicit authorized API commands do that. Identity
proof and session cookies are scoped to the configured installation/channel; that is not package or
Stable/Edge coexistence acceptance. Production HTTPS termination and private deployment wiring
remain deployment gates. The server uses one worker because authentication state is process-local.

## Fixed bounds

| Resource | Current bound |
|---|---|
| Login attempts | 128; five-minute absolute lifetime; expired attempts reclaimed |
| Active sessions | 256; one-hour absolute lifetime; no extension on proof/refresh/outage |
| Session policy constructor | Five minutes to eight hours; no lifetime CLI option yet |
| HTTP request body | 65,536 bytes, including chunked input; five-second receiving deadline |
| HTTP request headers | 100 headers / 16,384 aggregate bytes |
| Raw query | 8,192 bytes before parsing; duplicate fields rejected |
| Server concurrency / keep-alive | 64 / five seconds |
| Graceful server shutdown | Ten-second worker grace, then bounded owned-grant cleanup |
| Remote shutdown cleanup | At most two five-second revoke operations; discard all local credentials |

These are implementation bounds subject to the outstanding package/operations review, not a claimed
recovery-time SLA. [Protocol I/O bounds](ha-identity-protocol.md) are separately documented.

Origin/Host validation uses fixed configuration. Cookies are HttpOnly, SameSite=Lax and host-only;
HTTPS uses the __Host- prefix. Names include the installation/channel namespace. Development HTTP
has explicitly distinct cookie names. CSRF keys are private process memory and regenerate at restart.
Request forwarding/Ingress headers cannot change identity, callback, public origin or HA destination.

The command disables proxy-header rewriting and access logs, so OAuth callback queries are not logged.
Private HA wire logging is disabled. Logs contain allowlisted codes and cleanup counts, never raw
credentials or provider payloads. No credential is supplied as a CLI argument or stored in SQLite.

## Native package launcher

The installed Edge.3 domus-ha-app --channel edge entrypoint has fixed /data paths and UID/GID 65532.
Its only options.json field is public_origins:
an array of one to four distinct origins used to open HA, such as http://homeassistant.local:8123.
Scheme/host/port must be explicit and no path, query, credentials or fragment is accepted. Values
normalize through the same PublicOrigins adapter as the native CLI. The file is bounded to 16,384
bytes; unknown/duplicate fields and unsafe ownership/mode are rejected. It supplies no UUID: owned
storage generates one only on a valid empty first start. See [provisioning](owned-data-directory.md).
