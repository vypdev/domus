# Open Domus tasks in Home Assistant

Companion version `0.5.0` creates **Domus open tasks**, a native read-only to-do entity.
Each item shows one occurrence's title and current state. Draft, available,
assigned, in-progress and blocked occurrences appear, including work beyond
the first page in Domus. Separate occurrences with the same title have their
own identities. Completed, cancelled and skipped occurrences leave the list.
Reopening an occurrence restores its item identity.

The list refreshes once a minute. An empty successful read shows zero items.
**Unavailable** means a complete current read failed and hides the previous
items. More than 1,000 open occurrences makes the list unavailable until it fits
within the complete-read limit. Continue managing work in the
[Domus task workspace](../user-guide.md#task-workspace).

Anyone who can view this entity can see the titles and current states of every
open household occurrence. Configure this optional grant for that audience.

## Connect

1. Read the UUID and channel from the installation's private `installation.json`.
   Generate a dedicated bearer and digest in a private terminal.

   ```python
   from hashlib import sha256
   from secrets import token_hex
   from uuid import UUID

   installation = UUID(input("Domus installation UUID "))
   channel = input("Domus channel, edge or stable ").strip()
   if not installation.int or channel not in {"edge", "stable"}:
       raise SystemExit("Invalid installation or channel")
   bearer = f"{installation}.{channel}.tasks.{token_hex(32)}"
   print("Home Assistant task bearer", bearer)
   print("Domus SHA-256 digest", sha256(bearer.encode("ascii")).hexdigest())
   ```

2. In Supervisor, set `ha_tasks_digest` and restart Domus. Use the app's private
   address, such as `http://local-domus-edge:8100`. In standalone, set
   `DOMUS_HA_TASKS_DIGEST`, restart Domus and use its configured HTTPS origin.
   A reverse proxy terminating HTTPS must reach Domus over loopback.
3. Copy the complete [companion folder](../../custom_components/domus_calendar/)
   into Home Assistant's `custom_components` directory and restart Core.
   In **Settings → Devices & services → Add integration**, choose **Domus**,
   then **Open household tasks (read-only)**. Enter the address and task bearer.
   Select the discovered entity in a Home Assistant to-do view or dashboard.

Each configured installation/channel receives its own entity. Keep Home Assistant
backups private because its configuration entry contains the bearer. Rotate access
by setting the new digest, restarting Domus and using **Reconfigure** on the
existing entry. The entity retains its identity. Revoke access by removing the
digest and restarting Domus. A later valid connection restores the current list.

## Tareas abiertas en Home Assistant

**Tareas abiertas de Domus** muestra el título y estado de cada ocurrencia abierta.
Incluye borradores, tareas disponibles, asignadas, en curso y bloqueadas. Cada
ocurrencia tiene su propia identidad, aunque comparta título con otra. Completar,
cancelar u omitir una tarea la retira de la lista. Reabrirla recupera su identidad.
Gestiona el trabajo desde el espacio de tareas de Domus.

La lista se actualiza cada minuto. Una consulta vacía correcta muestra cero.
**No disponible** indica que falló la lectura completa y oculta los elementos
anteriores. Si hay más de 1.000 ocurrencias abiertas, reduce la lista hasta que
pueda consultarse completa. Quien vea la entidad podrá consultar todos sus títulos
y estados.

1. Consulta el UUID y el canal en `installation.json`. Genera el token de tareas
   y su resumen SHA-256 con el código anterior en una terminal privada.
2. Guarda el resumen en `ha_tasks_digest` en Supervisor o en
   `DOMUS_HA_TASKS_DIGEST` en standalone y reinicia Domus. Usa la dirección privada
   de la aplicación con el puerto `8100`, o el origen HTTPS en standalone.
3. Copia la carpeta completa de la integración en `custom_components` y reinicia
   Core. En **Ajustes → Dispositivos y servicios → Añadir integración**, elige
   **Domus** y **Tareas abiertas del hogar (solo lectura)**. Introduce la dirección
   y el token de tareas. Selecciona la entidad en una lista de tareas o un panel.

Protege las copias de seguridad de Home Assistant porque contienen el token.
Para rotarlo, cambia el resumen, reinicia Domus y usa **Reconfigurar** en la
entrada existente. Para revocar el acceso, elimina el resumen y reinicia Domus.
Al recuperar una conexión válida, la entidad vuelve a mostrar la lista actual.
