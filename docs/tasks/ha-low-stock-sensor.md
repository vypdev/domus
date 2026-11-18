# Native Home Assistant low-stock sensor

The Domus companion exposes **Domus low-stock products** as a read-only integer
sensor. It counts every product whose available stock after reservations is below
its replenishment minimum, using the same count as Domus Overview. Stock at the
minimum does not count. The sensor refreshes once a minute. Zero is a successful
read and **Unavailable** means the current count could not be read.

## Connect

1. Read the UUID and channel in the installation's private `installation.json`.
   Generate a bearer and its digest in a private terminal.

   ```python
   from hashlib import sha256
   from secrets import token_hex
   from uuid import UUID

   installation = UUID(input("Domus installation UUID: "))
   channel = input("Domus channel (edge or stable): ").strip()
   if not installation.int or channel not in {"edge", "stable"}:
       raise SystemExit("Invalid installation or channel")
   bearer = f"{installation}.{channel}.stock.{token_hex(32)}"
   print("Home Assistant stock bearer:", bearer)
   print("Domus SHA-256 digest:", sha256(bearer.encode("ascii")).hexdigest())
   ```

2. On Supervisor, set the digest in the `ha_stock_digest` app option and restart
   Domus. Use the app's private address on port `8100`, for example
   `http://local-domus-edge:8100`. On standalone, set `DOMUS_HA_STOCK_DIGEST`,
   restart Domus, and use its configured HTTPS origin. A reverse proxy
   terminating HTTPS must reach Domus over loopback.
3. Copy the complete [Domus companion folder](../../custom_components/domus_calendar/)
   into Home Assistant's configuration directory under `custom_components` and
   restart Core. In **Settings → Devices & services → Add integration**, choose
   **Domus** and select **Low-stock product count**. Enter the address and stock bearer.
   Use the discovered sensor entity in dashboards or conditions. Multiple installations
   have distinct entity registry identities.

Anyone who can view the entity can see the count. Open Domus Overview for
the products and quantities your household permissions allow. The calendar and
task deadline entries use their own bearers. Protect Home Assistant backups, which
contain the bearer saved in the integration entry.

To rotate a bearer, set the new digest in Domus and restart it. Use **Reconfigure**
on the existing integration entry to preserve the entity identity. To revoke access,
remove the digest and restart Domus. You can then remove the Home Assistant entry.

## Sensor de existencias bajas en Home Assistant

El sensor **Productos de Domus con existencias bajas** muestra el mismo
recuento que Inicio. Cuenta los productos cuyas existencias disponibles,
después de descontar las reservas, quedan por debajo de su mínimo.
Se actualiza cada minuto. Cero es un recuento válido. **No disponible**
indica que Home Assistant no ha podido consultar el recuento actual.

1. Consulta el UUID y el canal de la instalación en su archivo privado
   `installation.json`. Usa el código anterior en una terminal privada para
   generar el token y su resumen SHA-256.
2. Guarda el resumen en `ha_stock_digest` en Supervisor o en
   `DOMUS_HA_STOCK_DIGEST` en la instalación independiente y reinicia Domus.
   En Supervisor, usa la dirección privada de la aplicación con el puerto
   `8100`. En la instalación independiente, usa el origen HTTPS configurado.
   Si un proxy termina HTTPS, conéctalo a Domus por loopback.
3. Instala la [carpeta de integración](../../custom_components/domus_calendar/)
   completa en `custom_components` de Home Assistant y reinicia Core. En
   **Ajustes → Dispositivos y servicios → Añadir integración**, elige **Domus**
   y **Recuento de productos con existencias bajas**. Introduce la dirección y el token.

Quien pueda ver el sensor podrá consultar el recuento. En Inicio de Domus
puedes consultar los productos y cantidades que tus permisos permiten ver.
El calendario y los vencimientos usan sus propios tokens. Protege las copias
de seguridad de Home Assistant, que incluyen el token guardado en la entrada.

Para rotar el token, cambia el resumen y reinicia Domus. Usa **Reconfigurar**
en la entrada existente para conservar la identidad del sensor. Para revocar el
acceso, elimina el resumen y reinicia Domus. Después puedes eliminar la entrada
de Home Assistant.
