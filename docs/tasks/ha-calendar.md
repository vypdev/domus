# Native Home Assistant calendar

The Domus Calendar integration creates one read-only calendar for each connected
Domus installation and channel. Home Assistant displays planned work and due
dates. A date-only event occupies one day; a scheduled time or deadline appears
as a one-minute marker. Domus remains the source of the events. To change
anything, open Tasks in Domus.

Setup gives Home Assistant access to the household's planned and due events,
including their titles. Anyone with access to the calendar in Home Assistant
can see those events. Use a separate bearer for each Domus installation and
keep it in your password manager. Home Assistant stores the bearer in its
configuration entry; protect Home Assistant backups accordingly.

## Connect an installation

Use a Domus build that includes the native calendar endpoint and a compatible
[Home Assistant Core version](../compatibility-home-assistant.md). An older
installed Edge preview does not have this endpoint.

1. Read the Domus installation UUID from its private installation record
   (`instance_id` in `installation.json`). Use the running installation's
   channel, `stable` or `edge`.
2. Generate a random calendar bearer and its digest. For example, run the
   following Python snippet in a private terminal and follow its prompts:

   ```python
   from hashlib import sha256
   from secrets import token_hex
   from uuid import UUID

   installation = UUID(input("Domus installation UUID: "))
   channel = input("Domus channel (stable or edge): ").strip()
   if not installation.int or channel not in {"stable", "edge"}:
       raise SystemExit("Invalid installation or channel")
   bearer = f"{installation}.{channel}.{token_hex(32)}"
   print("Home Assistant calendar bearer:", bearer)
   print("Domus SHA-256 digest:", sha256(bearer.encode("ascii")).hexdigest())
   ```

3. Configure **only the digest** in Domus, then restart it:

   | Deployment | Operator setting | Address to enter in Home Assistant |
   | --- | --- | --- |
   | Standalone with persistent data | `DOMUS_HA_CALENDAR_DIGEST` in the server's environment | The configured HTTPS origin, for example `https://domus.example`. Keep certificate verification enabled. |
   | Supervisor app | `ha_calendar_digest` in the app options of a package that exposes this setting | The app's internal DNS name on port `8100`, for example `http://local-domus-edge:8100`. For a repository app, use its repository ID in place of `local`. |

   If a reverse proxy terminates standalone HTTPS, connect that proxy to
   Domus over loopback. Domus rejects direct remote HTTP on the calendar route.

   A compatible Supervisor package exposes `ha_calendar_digest` as an optional
   string in its options schema. The listener is private to the Supervisor
   network. It needs no published port, and it is separate from the Ingress
   listener on port `8099`. Leave the existing public origins unchanged.
4. Install the [Domus Calendar custom integration](../../custom_components/domus_calendar/manifest.json)
   by copying its complete `custom_components/domus_calendar` folder into the
   Home Assistant configuration directory. Restart Core. Under **Settings →
   Devices & services → Add integration**, choose **Domus** and select
   **Calendar**. Enter the
   Domus address and the bearer from step 2. The calendar is available in
   Home Assistant's **Calendar** view.

## Reconnect or revoke access

To rotate the bearer, generate a replacement with the same UUID and channel.
Replace the digest and restart Domus. In Home Assistant, choose **Reconfigure**
on the existing Domus Calendar entry and supply the new bearer. The old bearer
is rejected, and the calendar keeps its entity ID. An address change follows
the same reconfiguration path. A different installation or channel must be
added separately.

To revoke the connection, remove the Domus digest and restart Domus. You can
then remove the Home Assistant entry. No tasks or recurrence rules are removed.

## Read availability

The [task deadline sensors](ha-deadline-sensors.md) use a separate grant and
configuration entry. The calendar and sensors can run together.

Home Assistant refreshes the next event once per minute over the next 31 days.
Calendar reads allow up to 90 days and 1,000 events, in pages of up to 100. Use
a smaller range if a large read fails. A pending projection can show known
events with the pending status. If no known event intersects the requested
range, or any part of the read fails, Home Assistant reports the calendar as
unavailable. Normal polling retries after the source recovers. A successfully
read range with no events is shown as empty.
