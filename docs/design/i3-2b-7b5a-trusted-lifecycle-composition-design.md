# I3-2B.7B.5A — diseño de composición confiable para lifecycle de asociaciones

**Estado:** diseño publicado; implementación y pruebas de integración pendientes.  
**PR:** #16 — Draft, abierto y sin merge.  
**Dependencias validadas:** 7B.4A–7B.4E; 1,498 tests OK y compileall exit 0 según validación del propietario.  
**Alcance de este corte:** diseño únicamente. Sin cambios de código, runtime composition, HTTP, CLI, migraciones ni infraestructura.

## 1. Objetivo y criterio de seguridad

Definir cómo construir ProjectEnvironmentLifecycleService con dependencias confiables, usando el verifier criptográfico existente y una sola transacción SQLite para:
- revalidación de evidencia USER;
- lectura de identidad y grant Platform Admin;
- lectura/CAS de la asociación;
- escritura del evento lifecycle;
- commit atómico V26.

La fase no activa el caso de uso en runtime ni crea una superficie invocable. La construcción de la capacidad debe permanecer en una raíz de composición confiable, no en controladores, agentes ni datos de configuración suministrados por el caller.

## 2. Piezas existentes verificadas

### Verificador real

atlas.identity.verified_identity_context_service.VerifiedIdentityContextService implementa verify_in_unit_of_work(context, unit) y:
- valida el tipo y la vigencia temporal del contexto;
- verifica attestation mediante VerifiedIdentityContextAttestorPort;
- revalida issuer activo y perfil esperado;
- revalida binding activo y su revisión;
- resuelve la identidad USER canónica y comprueba identidad/revisión;
- no abre, confirma ni cierra la UoW recibida.

El puerto es VerifiedIdentityContextVerifierPort. El helper require_verified_owner_context_in_unit_of_work exige además USER activo, coincidencia de actor/UserId/revisión y ausencia de delegación.

**Decisión:** inyectar la instancia real de VerifiedIdentityContextService directamente como identity_verifier del servicio lifecycle. No introducir wrapper criptográfico ni duplicar validaciones.

### UoW y transacción

SQLiteLocalAuthorityUnitOfWorkFactory construye una SQLiteLocalAuthorityUnitOfWork, que hereda la transacción de SQLiteAuthorizationUnitOfWork y expone dentro de ella identity, platform_admin y workspaces. La transacción subyacente usa BEGIN IMMEDIATE.

El servicio lifecycle captura su Clock después de entrar en la UoW. El verifier real también consulta su Clock al revalidar evidencia dentro de esa misma transacción.

**Decisión:** una sola instancia de SQLiteLocalAuthorityUnitOfWorkFactory ligada al mismo SQLiteDatabase para el servicio lifecycle y para VerifiedIdentityContextService. Compartir también la misma instancia de Clock confiable y UTC evita relojes divergentes en la composición.

### Attestor

La composición recibe una implementación confiable de VerifiedIdentityContextAttestorPort, con clave provisionada fuera de la solicitud y fuera de la base de datos de negocio. Realm, audience y TTL son configuración interna explícita; no deben derivarse de OperationContext, request, headers ni atributos controlados por caller.

Este diseño no prescribe ni modifica el mecanismo de provisión de secretos del host. No se leen ni escriben secretos en este corte.

## 3. Frontera del ledger — decisión pendiente de implementación

El adapter SQLiteProjectEnvironmentLifecycleLedger actualmente acepta SQLiteUnitOfWork, mientras que el servicio recibe la SQLiteLocalAuthorityUnitOfWork. La composición no debe extraer unit._unit ni unit._unit._unit desde una closure: eso acopla el composition root a detalles privados y permite que el writer quede construido a partir de objetos no verificados.

Para 7B.5B se propone un cambio estrecho:
1. Ajustar el adapter para aceptar la UoW local de autoridad como contexto compartido, validar su tipo y resolver internamente la transacción SQLite.
2. La closure confiable ledger_factory recibirá la UoW y devolverá el adapter enlazado a esa misma transacción.
3. No añadir lifecycle_ledger ni un método writer a SQLiteLocalAuthorityUnitOfWork.
4. No exponer el adapter, closure ni factory de composición en puertos públicos o APIs de runtime.
5. La closure comprobará que recibió la UoW esperada y fallará cerrado ante cualquier otro objeto.

La escritura del ledger continúa siendo invocable desde código Python que importe deliberadamente el adapter; por tanto, esta frontera reduce exposición accidental, pero no constituye aislamiento contra código Python arbitrario con acceso al proceso. La seguridad depende de mantener la raíz de composición y los módulos de infraestructura fuera de superficies de extensión no confiables.

## 4. Raíz de composición propuesta

Crear en 7B.5B un módulo interno de composición, sin exportarlo desde atlas.__init__ ni registrarlo en runtime:
- recibe explícitamente SQLiteDatabase, Clock confiable, attestor confiable, realm/audience/TTL;
- construye exactamente un SQLiteLocalAuthorityUnitOfWorkFactory;
- construye VerifiedIdentityContextService con ese factory, Clock y attestor;
- construye una closure privada para SQLiteProjectEnvironmentLifecycleLedger que enlaza la UoW local a la transacción compartida;
- construye ProjectEnvironmentLifecycleService con factory, verifier real, Clock y closure;
- devuelve únicamente el servicio lifecycle a un caller interno de confianza.

No se acepta un VerifiedIdentityContext arbitrario como prueba suficiente: el servicio debe revalidarlo criptográficamente dentro de la transacción. El contexto debe proceder de la ruta de admisión de prueba nativa ya existente; 7B.5B no añadirá login ni endpoint de emisión.

## 5. Pruebas de integración requeridas en 7B.5B

Usar SQLite temporal y los componentes reales de producción para el camino de verificación:
- SQLiteLocalAuthorityUnitOfWorkFactory;
- VerifiedIdentityContextService;
- implementación real de attestor HMAC con clave efímera de test;
- repositorios SQLite reales y migraciones de test;
- ProjectEnvironmentLifecycleService;
- SQLiteProjectEnvironmentLifecycleLedger.

El fixture debe establecer una cadena nativa de prueba válida (issuer, binding, proof de un solo uso y USER canónico) usando APIs/repositorios de test existentes. No sustituir verify_in_unit_of_work por un mock.

Casos mínimos:
1. contexto emitido por Identity Authority válido + grant Platform Admin exacto → transición y evento confirmados juntos;
2. attestation alterada → DENY, cero escrituras;
3. issuer revocado/inactivo → DENY, cero escrituras;
4. binding revocado o con revisión distinta → DENY, cero escrituras;
5. USER desactivado o revisión canónica cambiada → DENY, cero escrituras;
6. contexto expirado → DENY, cero escrituras;
7. contexto para otra audience/realm → DENY;
8. contexto con actor/UserId discordante o delegación → DENY;
9. grant Platform Admin revocado/expirado o permiso incorrecto → DENY, cero escrituras;
10. fallo de persistencia/commit → rollback de evento, asociación y marcador;
11. prueba de que verifier y servicio observan la misma UoW física (identidad de conexión/transacción), sin abrir una segunda transacción durante verify;
12. prueba de superficie: composition builder no exporta writer ni habilita un endpoint/CLI/ruta de escritura paralela.

Los tests de rechazo deben verificar estado de asociación, revisión, número de eventos y marcadores, no solamente la excepción.

## 6. Restricciones y fuera de alcance

- No añadir endpoint HTTP, CLI, agente invocable ni runtime registration.
- No aplicar V26 a base productiva ni ejecutar bootstrap real.
- No cambiar systemd, Docker, usuarios, permisos, host, secretos ni configuración de producción.
- No hacer que el servicio lifecycle emita por sí mismo contextos de identidad.
- No permitir que un verifier alternativo sea elegido por request o configuración del usuario.
- No afirmar que el test HMAC demuestra seguridad del almacenamiento de la clave en producción.
- No convertir la UoW general en un contenedor de writers de auditoría.

## 7. Riesgos y decisiones que deben cerrarse antes de implementación

1. **Provisionamiento de clave HMAC:** identificar el adapter/fixture ya existente y reutilizarlo; no inventar una ruta de secretos ni persistir la clave en SQLite. Si no hay adapter adecuado, detenerse y proponer el contrato antes de añadir uno.
2. **Fixture de prueba nativa:** reutilizar el protocolo existente de Native Authentication; no crear atajos que inserten un VerifiedIdentityContext firmado a mano y luego llamen a eso verificación real.
3. **Frontera Python:** el módulo interno no puede impedir imports deliberados dentro del mismo proceso. La garantía es de arquitectura y superficie, no sandbox. Cualquier plugin/skill no confiable requiere aislamiento de proceso separado y no forma parte de este slice.
4. **UoW del ledger:** la adaptación debe validar tipo y compartir exactamente la transacción; no aceptar una conexión arbitraria ni abrir una UoW propia en el camino de servicio.

## 8. Secuencia de entrega

- **7B.5A (este documento):** decisiones y criterios de integración.
- **7B.5B:** adapter/raíz de composición mínima y pruebas de integración con verifier/attestor reales.
- **7B.5C:** pruebas adversariales complementarias y revisión de superficie, solo si 7B.5B pasa.
- No habilitar runtime/HTTP/CLI sin una decisión posterior y autorización explícita.

## 9. Estado

Diseño publicado para revisión. No se ha implementado 7B.5B, no se ha modificado código de producción y no se ha activado ninguna ruta operativa. PR #16 continúa Draft, abierto y sin merge.
