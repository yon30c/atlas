# B1-B-03C — Ciclo de vida de identidad y seguridad de cuentas

**Estado:** política técnica propuesta; los flujos operativos externos permanecen DESHABILITADOS.  
**Baseline:** B1-A-06 y B1-B-03A cerrados normativamente.  
**Dependencias:** B1-B-03B.

## 1. Objetivo

Especificar linking, unlinking, cambio de proveedor, recuperación, lifecycle de issuers y tratamiento de fusiones sin alterar las decisiones aprobadas ni habilitar operaciones antes de contar con autenticación verificable.

La regla principal es que la conveniencia de acceso nunca prevalece sobre la unicidad y continuidad de la identidad canónica.

## 2. Invariantes no negociables

1. Un UserId global corresponde a exactamente una Identity(USER), y viceversa.
2. Una Identity(USER) puede tener múltiples bindings externos.
3. Cada pareja exacta (issuer_id, subject) puede vincularse a como máximo una identidad.
4. Una pareja vinculada permanece reservada después de revocar su binding; nunca se reasigna.
5. Email, nombre, teléfono, avatar, dominio de correo o similitud de atributos no prueban identidad ni autorizan linking.
6. Linking/unlinking no cambia UserId, identity_id, propietario de Memory ni Grants.
7. Revocar un binding no revoca automáticamente la Identity(USER), pero sí invalida el acceso autenticado que dependía de ese binding.
8. Un binding nuevo no hereda Grants ni autorizaciones.
9. No hay merge automático de identidades.
10. Fallo, ambigüedad, evidencia incompleta o issuer no confiable producen DENY.

## 3. Linking de una cuenta externa

Precondiciones:
- sesión autenticada vigente para una Identity(USER) existente;
- reautenticación reciente según política del issuer/operación;
- prueba criptográfica reciente del control de la cuenta externa nueva;
- confirmación explícita del propietario;
- issuer ACTIVE y confiable;
- ausencia de binding previo de la pareja exacta (issuer_id, subject), incluido tombstone.

Secuencia:
1. Identity Authority crea una operación idempotente de linking asociada a UserId, identity_id, issuer, revisión esperada e idempotency key.
2. Authentication Authority valida la prueba externa contra issuer, audience, firma, nonce, expiración y subject exactos.
3. Identity Authority vuelve a resolver el issuer confiable y la revisión de Identity.
4. En una UoW, comprueba la unicidad de la pareja, inserta el binding ACTIVE y aumenta la revisión de Identity.
5. Consistency invalida contextos/admisiones que deban renovarse por cambio de binding/revisión.
6. Solo después de confirmación/reconciliación se informa linking completado.

Si el binding ya existe para la misma Identity, se devuelve resultado idempotente solo si la intención es idéntica y la operación original lo acredita. Si pertenece a otra Identity o está revocado, DENY; no se transfiere ni reactiva.

## 4. Unlink y revocación

Unlink es irreversible para ese binding.

Precondiciones:
- sesión verificada y reautenticación reciente;
- confirmación explícita de la cuenta/binding exactos;
- existencia de al menos otro método de acceso o recuperación utilizable, verificado y aprobado por política;
- issuer y binding identificados sin ambigüedad.

Secuencia:
1. Reservar operación con idempotencia semántica.
2. Comprobar que no elimina el último medio utilizable.
3. CAS del binding ACTIVE a REVOKED y aumento de su revisión.
4. Conservar tombstone y clave de unicidad de (issuer, subject).
5. Invalidar contextos/admisiones que dependan del binding.
6. Fencing confirmado y reconciliación antes de declarar terminado el proceso.

No se elimina físicamente el binding ni se libera su pareja. No se revocan otros bindings. No se cambia UserId/identity_id ni la propiedad de recursos.

**Fail-closed:** si no se puede probar que permanece un método utilizable, no se ejecuta unlink.

## 5. Cambio de proveedor

El cambio es una operación de linking de una cuenta nueva a la misma Identity(USER), seguida opcionalmente por unlink de la anterior.

Orden obligatorio:
1. Verificar la cuenta nueva.
2. Crear y confirmar el binding nuevo.
3. Confirmar que existe una vía de acceso/recuperación funcional.
4. Revocar el binding anterior si el propietario lo solicita.
5. Reconciliar contextos y admisiones.

No existe transferencia automática de UserId, identidad, memoria o permisos entre dos identidades distintas. No se elimina el binding antiguo para permitir su reutilización.

## 6. Recuperación de cuenta

La recuperación de cuenta queda DESHABILITADA hasta definir un procedimiento de prueba independiente y resistente a account takeover.

No son factores suficientes por sí solos:
- email o teléfono;
- nombre, fecha de nacimiento o atributos de perfil;
- UserId o identity_id;
- una sesión antigua;
- conocimiento de memorias, conversaciones o datos privados;
- una afirmación de un agente o administrador no respaldada por una política aprobada.

La política futura deberá definir:
- factores independientes y evidencia exigida;
- periodo de espera y notificaciones;
- tratamiento de cambios recientes de credenciales/issuer;
- protección contra SIM swap, phishing y takeover del correo;
- revisión de actividad anómala;
- procedimiento de disputa y recuperación;
- consecuencias para sesiones, bindings, contextos y admisiones;
- auditoría y recuperación ante error.

Hasta entonces, la pérdida de todos los métodos de acceso no autoriza crear una identidad nueva y reasignarle el UserId o recursos existentes.

## 7. Lifecycle y confianza de issuers

Estados propuestos:
- ACTIVE: se admiten nuevas verificaciones sujetas a validación completa.
- SUSPENDED: no se admiten nuevas verificaciones ni linking; los contextos dependientes se consideran no confiables hasta reevaluación.
- REVOKED: estado terminal; no se vuelve a confiar en esa entrada como si no hubiera ocurrido revocación.

Cambios de issuer:
- toda modificación de issuer/configuración/keyset aumenta revision;
- una revisión obsoleta no emite VerifiedIdentityContext;
- suspensión/revocación requiere invalidar contextos y admissions dependientes;
- pérdida de confianza no se resuelve por fallback a otro issuer;
- rotación normal de claves requiere periodo controlado de solapamiento y validación de key id/issuer/audience;
- compromiso de clave exige revocación de la clave afectada, invalidación de evidencia emitida bajo ella según la política, y reautenticación;
- si no puede determinarse qué evidencia depende de una clave comprometida, se bloquea el issuer completo.

Los estados y su efecto sobre sesiones/admisiones se deben coordinar por Consistency. Identity Authority mantiene el estado canónico del issuer; Consistency no lo modifica.

## 8. Fusión de identidades

Merge está DESHABILITADO.

No se fusionan identidades por:
- coincidencia de email;
- mismo nombre/teléfono;
- cuentas del mismo proveedor;
- petición de un caller;
- similitud de actividad o recursos.

Una futura operación requerirá un procedimiento independiente con:
- prueba reciente y fuerte de control de ambas identidades;
- consentimiento explícito de ambas, cuando ambas sean accesibles;
- inventario de memorias, proyectos, grants, autorizaciones, bindings y dependencias;
- decisión explícita sobre cada recurso y su propietario;
- resolución de conflictos de identidad y unicidad;
- revisión de seguridad y auditoría;
- fencing e invalidación de todas las admissions afectadas;
- tombstone de identidad absorbida y reserva de todos sus IDs/bindings;
- pruebas de recuperación y rollback.

No hay transferencia implícita de recursos, owner_id, Grants o PRIVATE authorizations. Hasta que el procedimiento sea aprobado, cualquier solicitud de merge se rechaza.

## 9. Concurrencia e idempotencia

- Toda mutación incluye expected_revision y una idempotency key.
- La misma clave con intención semántica idéntica recupera la operación original.
- La misma clave con intención distinta produce conflicto.
- UNIQUE(issuer_id, subject fingerprint) arbitra linking concurrente.
- CAS de revisión evita dos mutaciones incompatibles.
- La revocación es monotónica; no existe transición REVOKED→ACTIVE.
- Timeout o resultado externo ambiguo conserva operación en estado unresolved/blocked; nunca se interpreta como éxito ni como cancelación.
- No se libera fencing sin evidencia confirmada y reconciliada.

## 10. Criterios de salida

- Linking requiere cuenta existente autenticada + prueba reciente de cuenta nueva + confirmación explícita.
- Unlink no puede eliminar el último método utilizable.
- Cambio de proveedor añade el nuevo binding antes de revocar el anterior.
- Issuer suspendido/revocado no emite contexto.
- Merge y recovery permanecen deshabilitados sin política aprobada.
- Tombstones y unicidad sobreviven a restart/restore.
- Ninguna mutación cambia UserId, identity_id o propietario de Memory.

**Resultado B1-B-03C:** política de lifecycle definida con bloqueos explícitos. No habilita linking, unlink, recovery, merge ni proveedores externos.
