# Protocolo de escritura de archivos del workspace

> Estado: implementación del Ciclo 2 publicada; validación local pendiente.
> Rama: `feature/terminal-commands`.
> Alcance: staging, commit y evaluación de recuperación para archivos de prueba.
> No concede autorización CAM ni habilita el runtime.

## 1. Objetivo

Permitir que un servicio de aplicación prepare un cambio de archivo, lo confirme explícitamente y pueda inspeccionar el estado durable después de una interrupción. La preparación no modifica el destino final.

Este protocolo es una frontera de consistencia del sistema de archivos. No reemplaza la autorización de operaciones, el coordinador CAM, el fencing ni la aprobación humana.

## 2. Contrato de operación

Cada escritura identifica:

- `workspace_id`: workspace registrado en la composición local;
- `operation_id`: UUID canónico que actúa como clave idempotente;
- `path`: ruta relativa POSIX normalizada dentro del workspace;
- `content`: texto UTF-8;
- `expected_sha256`: hash esperado del archivo actual, o `None` únicamente para crear un archivo que no exista.

El contenido está limitado a 1 MiB por defecto. No se admiten rutas absolutas, traversal, componentes vacíos, enlaces simbólicos ni la ruta reservada `.atlas-staging`. Los directorios padre deben existir.

Para actualizar un archivo se exige el hash del contenido actual. Si el destino cambia antes del commit, la operación se detiene con conflicto en lugar de sobrescribir el cambio detectado.

## 3. Persistencia del staging

El adaptador mantiene los registros dentro de:

```text
<workspace>/.atlas-staging/<operation_id>/
    payload
    manifest.json
```

- El directorio de staging es reservado, no aparece en listados y no puede leerse mediante `workspace.read`.
- El payload se escribe de forma exclusiva, se sincroniza con `fsync` y se valida mediante SHA-256.
- El manifest JSON contiene versión de esquema, workspace, operación, destino, hash esperado, hash nuevo, tamaño y estado.
- El manifest se sustituye atómicamente y su directorio se sincroniza.
- Repetir el mismo `operation_id` con el mismo binding es idempotente. Reutilizarlo con contenido o destino distintos produce conflicto.

## 4. Estados y transición

```text
STAGED
  |
  v
COMMITTING
  |
  v
COMMITTED
```

- `STAGED`: payload y manifest persistidos; el destino no se ha modificado.
- `COMMITTING`: intención de aplicar el cambio persistida antes de tocar el destino.
- `COMMITTED`: efecto de archivo aplicado y directorio de destino sincronizado.

Para crear se usa un hard link exclusivo que falla si el destino apareció. Para actualizar se usa `os.replace` después de comprobar el hash esperado. Los commits del adaptador se serializan con locks locales por destino.

## 5. Recuperación

`assess_recovery(workspace_id, operation_id)` es de solo lectura y clasifica:

| Estado | Significado |
|---|---|
| `STAGED_READY` | Staging completo; el destino aún coincide con el hash esperado |
| `COMMIT_CONFIRMED` | El manifest quedó en COMMITTING, pero el destino ya contiene el nuevo hash |
| `COMMIT_NOT_APPLIED` | El manifest quedó en COMMITTING, el destino conserva el hash anterior y el payload existe |
| `COMMITTED` | El manifest registra el commit completado |
| `CONFLICT` | El destino o payload no coincide con el estado esperado |
| `CORRUPT` | Manifest ausente, inválido o binding no verificable |

La evaluación no repara, no elimina staging y no ejecuta un commit. Si el estado es `COMMIT_NOT_APPLIED`, el propietario/caso de uso debe decidir explícitamente si reintenta `commit_write`. Si es `COMMIT_CONFIRMED`, un reintento explícito de commit reconcilia el manifest con el efecto ya aplicado.

No hay rollback automático ni restauración del contenido anterior. La recuperación nunca convierte incertidumbre en éxito.

## 6. Límites y garantías

- La atomicidad del rename/link se limita a la operación local del sistema de archivos; no es una transacción con SQLite.
- Los locks solo coordinan instancias cooperativas de este adaptador. No bloquean ediciones externas que ignoren esos locks.
- El hash detecta cambios observados antes del commit, pero no constituye un CAS del kernel para actualizaciones ni una garantía contra un escritor externo concurrente.
- El protocolo no autentica el workspace, al actor ni al propietario.
- No verifica Grants, identidad, proyecto, entorno, aprobaciones ni invalidaciones.
- No se añadió `workspace.write` a `IntentKind` o `CapabilityCatalog`.
- El servicio/adaptador no está compuesto en `cli.py`, consola ni runtime.

Antes de exponer escritura a Atlas conversacional, debe existir el gate de aplicación con autorización CAM y garantía de consistencia/fencing apropiadas. El protocolo de archivos es necesario, pero no suficiente.

## 7. Pruebas incluidas

- staging no altera el destino;
- creación y actualización con hash esperado;
- retry idempotente y rechazo de reutilización de operation ID;
- conflicto si el destino cambia o aparece después del staging;
- rechazo de traversal, rutas reservadas, symlinks y payload excesivo;
- detección de corrupción del manifest;
- recuperación de crash simulado después del reemplazo;
- validación del servicio de aplicación y aislamiento del staging respecto a lectura/listado.
