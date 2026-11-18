# Native Home Assistant shopping list

The Domus companion creates **Domus shopping list** as a read-only to-do entity.
It lists the items and quantities currently left to buy in Domus, including lines
beyond the first 25 shown in Overview. It refreshes once a minute. An empty list
means nothing is left to buy. **Unavailable** means the current list could not be
read, and Home Assistant stops showing the previously read items. A list of more
than 1,000 outstanding lines is unavailable until it fits in one complete read.

Anyone who can view the entity can see its item names and quantities. Use Domus to
edit the household list, record a purchase or post a receipt.

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
   bearer = f"{installation}.{channel}.shopping.{token_hex(32)}"
   print("Home Assistant shopping bearer:", bearer)
   print("Domus SHA-256 digest:", sha256(bearer.encode("ascii")).hexdigest())
   ```

2. On Supervisor, set the `ha_shopping_digest` app option and restart Domus.
   Use the app's private address, for example `http://local-domus-edge:8100`.
   On standalone, set `DOMUS_HA_SHOPPING_DIGEST`, restart Domus and use the
   configured HTTPS origin. A reverse proxy terminating HTTPS must reach
   Domus over loopback.
3. Copy the complete [Domus companion folder](../../custom_components/domus_calendar/)
   into Home Assistant's configuration directory under `custom_components`
   and restart Core. In **Settings → Devices & services → Add integration**,
   choose **Domus** and **Shared shopping list (read-only)**. Enter the address
   and shopping bearer. Use the discovered entity in the Home Assistant
   to-do view or on a dashboard. Each connected installation has its own entity.

Protect Home Assistant backups because the integration entry contains the bearer.
To rotate it, set the new digest, restart Domus and use **Reconfigure** on the
existing entry to preserve its entity identity. To revoke access, remove the digest
and restart Domus. You can then remove the Home Assistant entry.

## Lista de la compra en Home Assistant

La **Lista de la compra de Domus** es una lista nativa de solo lectura con los
artículos y cantidades pendientes de compra, incluidas las filas que quedan fuera
de las primeras 25 de Inicio. Se actualiza cada minuto. Una lista vacía indica que
no queda nada por comprar. **No disponible** indica que Home Assistant no pudo
obtener la lista actual y deja de mostrar los artículos anteriores. Si la lista
supera las 1.000 líneas pendientes, se muestra como no disponible hasta que vuelva
a poder consultarse completa.

Quien pueda ver la entidad podrá consultar los nombres y cantidades. Abre Domus
para editar la lista, registrar una compra o contabilizar una recepción.

1. Consulta el UUID y el canal en el archivo privado `installation.json` de la
   instalación. Usa el código anterior en una terminal privada para generar el
   token y su resumen SHA-256.
2. Guarda el resumen en `ha_shopping_digest` en Supervisor o en
   `DOMUS_HA_SHOPPING_DIGEST` en la instalación independiente. Reinicia Domus.
   En Supervisor, usa la dirección privada de la aplicación con el puerto
   `8100`. En la instalación independiente, usa el origen HTTPS configurado.
   Si un proxy termina HTTPS, conéctalo a Domus por loopback.
3. Instala la [carpeta de integración](../../custom_components/domus_calendar/)
   completa en `custom_components` y reinicia Core. En **Ajustes →
   Dispositivos y servicios → Añadir integración**, elige **Domus** y
   **Lista de la compra compartida (solo lectura)**. Introduce la dirección
   y el token. La entidad aparecerá en las listas de tareas de Home Assistant
   y se puede añadir a un panel.

Protege las copias de seguridad de Home Assistant porque contienen el token.
Para rotarlo, cambia el resumen, reinicia Domus y usa **Reconfigurar** en la
entrada existente. La entidad conserva su identidad. Para revocar el acceso,
elimina el resumen y reinicia Domus. Después puedes eliminar la entrada de Home
Assistant.
