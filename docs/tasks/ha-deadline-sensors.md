# Native Home Assistant task deadline sensors

Domus supplies **tasks due today** and **overdue tasks** as read-only Home
Assistant sensors. The counts match Overview. An available sensor can show
zero. An unavailable sensor means Home Assistant could not get a current
count. One refresh updates both sensors.

## Connect

1. Read the installation UUID (`instance_id` in the private
   `installation.json`) and channel (`edge` or `stable`). Generate a
   separate deadline bearer and digest in a private terminal.

   ```python
   from hashlib import sha256
   from secrets import token_hex
   from uuid import UUID

   installation = UUID(input("Domus installation UUID: "))
   channel = input("Domus channel (edge or stable): ").strip()
   if not installation.int or channel not in {"edge", "stable"}:
       raise SystemExit("Invalid installation or channel")
   bearer = f"{installation}.{channel}.deadlines.{token_hex(32)}"
   print("Home Assistant deadline bearer:", bearer)
   print("Domus SHA-256 digest:", sha256(bearer.encode("ascii")).hexdigest())
   ```

2. Configure the digest in Domus and restart it. On Supervisor, enter
   `ha_deadline_digest` in the app's options. The private app address uses
   port `8100`, for example `http://local-domus-edge:8100`. On standalone,
   set `DOMUS_HA_DEADLINE_DIGEST` and use the configured HTTPS origin.
   When a reverse proxy terminates HTTPS, it must connect to Domus over
   loopback.
3. Install the complete [Domus companion folder](../../custom_components/domus_calendar/manifest.json)
   in Home Assistant's configuration directory and restart Core. In
   **Settings → Devices & services → Add integration**, choose **Domus**
   and select **Task deadline counts**. Enter the address and deadline
   bearer. Use the two sensors in a dashboard or as automation conditions.

Anyone with access to the Home Assistant entities can see the two household
counts. The grant exposes no task details. The [native calendar](ha-calendar.md)
uses its own bearer and configuration entry. Home Assistant stores its bearer
in the entry, so protect Home Assistant backups accordingly.

## Recover or revoke

If both sensors become unavailable, check that Domus is running and the
address and digest are current. Home Assistant retries once a minute.
After rotating the bearer and restarting Domus, use **Reconfigure** on
the existing deadline entry to preserve both entity IDs. Removing the
digest and restarting Domus revokes access. You can then remove the
Home Assistant entry.

## Sensores de vencimientos en Home Assistant

Domus publica dos sensores de solo lectura, **Tareas de Domus que vencen
hoy** y **Tareas atrasadas de Domus**. Los recuentos coinciden con Inicio.
Un cero es un recuento válido. **No disponible** indica que Home Assistant
no pudo obtener un recuento actualizado. Los dos sensores se actualizan juntos.

1. Consulta el UUID de la instalación en su archivo privado
   `installation.json` y el canal (`edge` o `stable`). Ejecuta el
   código anterior en una terminal privada para generar un token y su
   resumen SHA-256.
2. Guarda el resumen en `ha_deadline_digest` si usas Supervisor, o en
   `DOMUS_HA_DEADLINE_DIGEST` si usas la instalación independiente.
   Reinicia Domus. En Supervisor, usa la dirección privada de la aplicación
   con el puerto `8100`. En la instalación independiente, usa el origen HTTPS
   configurado. Si un proxy termina HTTPS, conéctalo a Domus por loopback.
3. Copia la [carpeta de la integración](../../custom_components/domus_calendar/manifest.json)
   en la configuración de Home Assistant y reinicia Core. En
   **Ajustes → Dispositivos y servicios → Añadir integración**, elige
   **Domus**, selecciona **Recuentos de vencimientos** e introduce la
   dirección y el token.

Las personas con acceso a estas entidades pueden ver los dos recuentos
del hogar. Los detalles de las tareas siguen en Domus. El calendario
usa su propio token. Protege las copias de seguridad de Home Assistant,
que incluyen el token guardado en la entrada.

Si los sensores están **No disponibles**, comprueba que Domus siga activo
y que la dirección y el resumen sean los actuales. Home Assistant reintenta
la lectura cada minuto. Para rotar el token, reemplaza el resumen en Domus,
reinícialo y elige **Reconfigurar** en la entrada existente. Los sensores
conservan sus identificadores. Para revocar el acceso, elimina el resumen
y reinicia Domus. Después puedes eliminar la entrada de Home Assistant.
