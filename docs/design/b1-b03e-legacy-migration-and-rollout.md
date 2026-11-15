# B1-B-03E — Migración legacy, transición y puesta en servicio

**Estado:** estrategia de migración propuesta; no se migraron datos ni se ejecutaron cambios.  
**Dependencias:** B1-B-03B, B1-B-03C y B1-B-03D.  
**Límite:** ningún fallback silencioso entre identidad nueva y legacy.

## 1. Objetivo

Definir una transición verificable desde contratos y registros legacy hacia Identity Authority sin reasignar usuarios, alterar propietarios, convertir estados por semejanza o perder trazabilidad.

## 2. Fuentes legacy conocidas

- `Identity`: identity_id, kind, status y revision.
- `AuthenticatedUserSubject`: actor_identity_id, subject_user_id, is_active y revision.
- `IdentitySubjectBindingPort`: resolución legacy actor→subject_user_id.
- `AtlasIdentityBindingAdapter`: adaptador neutral hacia Memory Engine.

El contrato legacy no demuestra que `subject_user_id` sea un subject externo de proveedor ni que sea UserId canónico. No se presupone que la fuente sea persistente o que incluya issuer_id.

## 3. Inventario previo obligatorio

Antes de una migración se debe producir un inventario inmutable que incluya:
- origen, commit y versión de esquema;
- conteo de identidades por tipo y estado;
- conteo de bindings y estado;
- identidad/subject exactos con referencias opacas;
- revisiones y relaciones existentes;
- duplicados y conflictos;
- consumidores/proyectos relacionados solo cuando la fuente autorizada lo permita;
- checksums del inventario y evidencia de extracción;
- exclusión explícita de credenciales, tokens y contenido Memory.

No publicar subjects, emails ni otros identificadores personales en reportes generales. El inventario completo requiere almacenamiento restringido y protección apropiada.

## 4. Clasificación de registros

Cada registro se clasifica en uno de estos grupos:

1. **Migrable con evidencia:** origen autoritativo demuestra la correspondencia exacta entre registro legacy, Identity(USER), UserId canónico y binding, si existe.
2. **Requiere resolución:** faltan issuer, procedencia, unicidad, prueba de control o relación 1:1.
3. **No migrable automáticamente:** duplicados, conflictos, estados ambiguos, subject sin issuer, identidad revocada o evidencia no verificable.
4. **No USER:** AGENT/WATCHER/SYSTEM/SERVICE; se preserva sin atribuirle VerifiedIdentityContext ni permisos nuevos.

Ningún registro del grupo 2 o 3 recibe una identidad canónica por inferencia.

## 5. Reglas de mapeo

- `subject_user_id` no se copia directamente a UserId ni a subject externo.
- Solo una autoridad interna aprobada puede emitir un UserId nuevo.
- El vínculo con Identity(USER) debe probarse de forma 1:1.
- Email, nombre, teléfono, igualdad textual, orden de creación o coincidencia de actividad no constituyen evidencia.
- Legacy ACTIVE/SUSPENDED/REVOKED conserva su semántica. No se convierte a ACTIVE/INACTIVE/DELETING/DELETED.
- REVOKED no se reactiva.
- No se crea binding externo sin issuer confiable y prueba criptográfica verificada.
- Memory.owner_id permanece intacto. No se reescriben propietarios para hacer coincidir el nuevo modelo.
- No se migran ni heredan Grants/PRIVATE authorizations a partir de una identidad nueva sin reglas CAM explícitas.

## 6. Estrategia de transición

Fases propuestas:

### M0 — Read-only inventory
Extraer inventario y comprobar consistencia. No escribir Identity Authority.

### M1 — Mapping manifest
Crear manifiesto firmado/verificable de mappings aprobados, con origen, destino, evidencia y motivo. Los casos ambiguos permanecen sin mapping. El manifiesto no contiene credenciales ni payloads.

### M2 — Dry run
Ejecutar migrador contra copia desechable de SQLite v4. Comparar conteos, cardinalidad, constraints, uniqueness, tombstones, FK y checksums. No se conecta a servicios activos.

### M3 — Controlled write
Tras aprobación específica, aplicar migración v5 y mappings aprobados en DB de prueba. No activar autenticación externa ni emitir contextos todavía.

### M4 — Verification
Verificar cada relación UserId↔Identity(USER), binding exacto, estado, revisión, tombstones, integridad, foreign_key_check y ausencia de duplicados. Casos sin prueba permanecen bloqueados.

### M5 — Explicit cutover
Un corte controlado requiere ventana de mantenimiento, backup restaurable, gate cerrado, operaciones mutadoras detenidas, revisión de diffs, verificación post-migración y plan de recuperación. Solo se habilita el flujo que tenga issuer y política aprobados.

## 7. Política de lectura y compatibilidad

- No dual-read abierto ni fallback automático nuevo→legacy.
- La transición puede usar un adaptador explícito, limitado a registros incluidos en el mapping manifest y con versión de política declarada.
- El adaptador no emite VerifiedIdentityContext por sí mismo.
- Un fallo de Identity Authority no activa el adaptador legacy como alternativa.
- Los consumidores no pueden seleccionar qué identidad resolver.
- Toda respuesta ambigua o registro fuera del manifiesto produce DENY.
- La compatibilidad temporal se retira solo después de comprobar consumidores, logs y pruebas; la retirada requiere cambio explícito.

## 8. Backup, restore y rollback

Antes de migrar:
- backup consistente con DB cerrada o mecanismo SQLite de backup soportado;
- checksum, integridad y permisos del archivo;
- copia de configuración no secreta y referencias de secretos protegidas por separado;
- prueba de restauración sobre destino aislado;
- inventario de versión, migrations y commit exactos.

Después de migrar:
- PRAGMA integrity_check;
- PRAGMA foreign_key_check;
- comparación de conteos y hashes de inventario;
- comprobación de migrations 1–5 y checksums;
- verificación de tombstones, unicidad y revisiones;
- gate permanece cerrado hasta completar reconciliación.

No se hace downgrade destructivo tras aceptar nuevas escrituras. Restaurar un backup anterior puede reintroducir bindings revocados, sesiones o admissions antiguas; por tanto, se requiere reconciliación independiente y fencing con generación superior antes de abrir el gate. Un restore anterior a Forget requiere volver a ejecutar inventario y supresión; nunca se declara olvidado por el recibo histórico solamente.

## 9. Criterios de aceptación

- Cada mapping tiene procedencia y evidencia verificable.
- Ningún UserId se deriva de subject_user_id.
- No hay colisiones ni reutilización de issuer/subject.
- No se convierten estados legacy automáticamente.
- Memory.owner_id no cambia.
- Grants y PRIVATE authorization no se heredan por migración.
- Registros ambiguos permanecen bloqueados.
- La migración v5 conserva todas las filas v4 y las FK.
- Restore anterior a revocación/fencing no reabre operaciones.
- No existe fallback silencioso.
- El cutover es reversible solo antes de nuevas escrituras; después requiere recuperación/reconciliación, no downgrade ingenuo.

## 10. Condiciones que impiden el cutover

El cutover no se ejecuta si:
- no hay backup restaurable;
- inventario tiene conflictos sin resolver;
- la autoridad emisora de UserId no está activa y protegida;
- no se puede probar relación 1:1;
- issuer no está confiable o protocolo no está validado;
- la protección de subject/key material no está resuelta;
- migración no supera pruebas de v1→v5, v4→v5 y preservación;
- hay operación de Consistency unresolved o fencing no confirmado;
- no se puede asegurar que el gate siga cerrado durante el corte.

**Resultado B1-B-03E:** transición y rollback/recovery definidos; migración real y activación permanecen deshabilitadas hasta aprobación de ejecución y cierre de bloqueos.
