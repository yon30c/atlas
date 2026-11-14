# ME-03K — Almacén local de proyecciones de checkpoint

**Estado:** primer adaptador implementado en la rama de trabajo; pendiente de validación del propietario.  
**Perfil:** local, un solo host.  
**No incluye:** Trust Anchor externo, anti-rollback, integración con el escritor SQLite ni cambios de esquema.

## 1. Separación de responsabilidades

- `LocalCheckpointProjectionPublisherPort` publica artefactos ya codificados.
- `LocalConsistencyCheckpointProjectionPort` resuelve las referencias durante recuperación.
- `FilesystemCheckpointProjectionStore` implementa ambos límites, sin depender de SQLite.
- El coordinador/escritor futuro debe publicar y verificar los artefactos antes de iniciar la transacción SQLite.

El adaptador no modifica el journal ni crea checkpoints. Tampoco decide la política de confianza: recibe una solicitud construida con la política local ya seleccionada.

## 2. Organización del almacén

La raíz es una ruta absoluta, existente y suministrada explícitamente al construir el adaptador. No se fija una ruta de producción ni se crean montajes o servicios.

Dentro de ella:

- `state/<sha256-hex>`: bytes canónicos de la proyección.
- `integrity/<sha256-hex>`: bytes canónicos del manifiesto.

Las referencias externas conservan el formato opaco `sha256:<64 hex minúsculas>`. No son rutas, URLs ni nombres proporcionados libremente por el journal.

## 3. Publicación

1. Validar codec, manifiesto y referencias antes de escribir.
2. Escribir el objeto de estado en un temporal del mismo directorio.
3. Hacer flush y `fsync` del archivo.
4. Publicar mediante hard link sin reemplazo; si el objeto ya existe, aceptar solo bytes idénticos.
5. Eliminar el temporal y hacer `fsync` del directorio.
6. Repetir para el manifiesto, después del estado.
7. Leer ambos objetos desde sus rutas definitivas y ejecutar de nuevo la validación del codec.
8. Devolver éxito solo después del read-back completo.

Una interrupción entre la publicación del estado y la del manifiesto puede dejar un objeto de estado huérfano. Es aceptable: SQLite todavía no debe apuntar a él. No se intenta una transacción distribuida entre archivos y SQLite.

Los objetos publicados nunca se reemplazan. Una colisión con bytes distintos produce error y conserva el objeto existente.

## 4. Resolución y clasificación

La resolución verifica:

- Referencias SHA-256 exactas y bytes canónicos.
- Compromiso del estado y compromiso del manifiesto.
- Correspondencia de checkpoint ID, dominio, época y secuencia.
- Política solicitada y versiones de esquema/reducer permitidas.
- Reconstrucción estricta de la proyección y su forma tipada.

Clasificación:

- Objeto ausente o almacén inaccesible: `UNAVAILABLE`.
- Referencia malformada, bytes alterados o metadata contradictoria: `REJECTED`.
- Solo la coincidencia íntegra y exacta permite devolver evidencia `VERIFIED`, que aún pasa por `require_verified_checkpoint_projection()` en el verificador.

La autenticación de la referencia del checkpoint depende de la cadena autenticada del journal que se verifica antes de llamar al puerto de proyección. El manifiesto y sus hashes no sustituyen esa autenticación.

## 5. Seguridad y límites

- La raíz debe provisionarse y protegerse fuera de SQLite. El adaptador exige que exista y no sea un symlink; no cambia propietarios, permisos ni ACLs del host.
- Los archivos temporales se crean con permisos restrictivos del sistema y se publican sin sobrescritura.
- La protección local del directorio no equivale a almacenamiento remoto ni a una autoridad monotónica independiente.
- Una restauración coherente y antigua del almacén junto con el journal sigue fuera de la capacidad de detección del perfil local.
- No se declara resistencia a manipulación por un atacante con control del usuario/host que ejecuta Atlas.
- No se ha integrado aún el publisher con un coordinador de checkpoint ni con la transacción SQLite.

## 6. Validación pendiente

Pruebas previstas para el propietario:

- Publicación y resolución exactas.
- Reintento idempotente.
- Objeto ausente y objeto corrupto.
- Colisión sin sobrescritura.
- Política y versiones incompatibles.
- Raíz inválida.
- Después de las pruebas unitarias, suite completa.

No ejecutar despliegues, crear directorios operativos ni seleccionar una ruta persistente de producción como parte de esta fase.


## 7. Evidencia de proyección para el coordinador

La verificación local completa ya produce la proyección reducida junto con
`VerifiedLocalConsistencyRecoveryState`. El campo `projection` se incluye
solo después de verificar cadena HMAC, política, resolución de checkpoint
(si existe), replay semántico e inventarios. La evidencia comprueba que la
proyección coincide con dominio, época, head y versión de metadatos de replay.

Esto evita que un coordinador vuelva a reducir datos estructurales por su
cuenta o use una proyección que no sea el resultado de la ruta de recuperación
verificada. El coordinador de escritura deberá exigir esta evidencia y volver
a comprobar dominio, época, secuencia y commitment dentro de la transacción
SQLite antes de insertar el nuevo checkpoint.

La proyección adjunta no añade anti-rollback externo ni convierte el almacén
filesystem en autoridad de confianza.
