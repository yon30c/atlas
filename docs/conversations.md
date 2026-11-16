# Conversaciones locales de Atlas

## Persistencia (fase 2D)

Atlas guarda las conversaciones en una base SQLite independiente de la base de autoridad:

`~/.local/state/atlas/conversations.sqlite3`

- Directorio dedicado: modo `0700`.
- Archivo SQLite: modo `0600`.
- El arranque recupera la conversación activa; solo crea otra cuando no hay una activa válida.
- El historial se conserva completo. El límite de ocho turnos y 2.000 caracteres se aplica únicamente al contexto enviado al modelo.
- La base no se sincroniza ni se respalda automáticamente.
- Si no puede preparar o abrir el almacenamiento, Atlas falla al iniciar; no degrada silenciosamente a memoria.

Se puede aislar otra base con el parámetro `conversation_db_path` de `main()` o con `ATLAS_CONVERSATION_DB`.

## Gestión (fase 2E)

Comandos disponibles:

| Comando | Acción |
|---|---|
| `/new [título]` | Crea y selecciona una conversación |
| `/conversations` | Lista conversaciones activas |
| `/conversations --all` | Incluye conversaciones cerradas |
| `/use ID` | Cambia la conversación activa |
| `/rename título` | Renombra la conversación activa |
| `/close` | Cierra la activa y crea una nueva |

El gestor de aplicación no depende de la consola ni del proveedor LLM.

## Exportación portable (fase 2G)

- `/export "/ruta/absoluta/conversacion.json"`: exporta la conversación activa.
- `/export CONVERSATION_ID "/ruta/absoluta/conversacion.json"`: exporta una conversación concreta, incluso si está cerrada.
- El JSON incluye versión de formato, metadatos y el historial íntegro en orden.
- El archivo se crea con modo `0600`; el comando no sobrescribe archivos existentes ni sigue enlaces simbólicos.
- La exportación es texto legible **sin cifrar**. Debe guardarse en un directorio privado y protegerse como información personal. Para conservar una copia cifrada de toda la base, utiliza `/backup`.

## Protección y recuperación (fase 2F)

- `/backup "/ruta/absoluta/atlas.atlasbackup"`: crea un snapshot SQLite consistente cifrado.
- `/verify-backup "/ruta/atlas.atlasbackup"`: verifica contraseña, autenticidad, integridad SQLite y checksums de migración.
- `/restore-backup "/ruta/atlas.atlasbackup" "/directorio-privado/conversations.sqlite3"`: restaura en una ruta nueva, sin sobrescribir una base existente.
- `/delete ID CONFIRM`: elimina explícitamente una conversación y sus mensajes de la base activa.

Los respaldos usan derivación de clave scrypt (N=32768, r=8, p=1) y AES-256-GCM con salt y nonce aleatorios. Se requiere una contraseña de al menos 12 caracteres. Los archivos de respaldo se crean con modo `0600`; el destino de restauración debe estar dentro de un directorio propiedad del usuario y sin permisos para grupo/otros (normalmente `0700`).

Ejemplo de restauración:

1. Crear un directorio nuevo y privado: `mkdir -m 700 -p ~/.local/state/atlas-restored`.
2. Ejecutar `/restore-backup` indicando ese directorio y un nombre de base nuevo.
3. Salir de Atlas.
4. Iniciar con `ATLAS_CONVERSATION_DB="$HOME/.local/state/atlas-restored/conversations.sqlite3" atlas`.

La restauración no reemplaza la base actual. Verifica el respaldo antes de escribir la nueva base.

**Límite importante de eliminación:** `/delete` elimina lógicamente los registros de la base activa. No garantiza borrado forense de bloques ya liberados, snapshots del sistema de archivos ni copias contenidas en respaldos anteriores. Los respaldos cifrados conservan su contenido hasta que el usuario los elimine.

No hay respaldos automáticos ni sincronización externa.
