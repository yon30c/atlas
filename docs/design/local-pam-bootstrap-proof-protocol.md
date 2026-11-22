# Protocolo de prueba para autenticación y decisión directa del bootstrap LOCAL

**Estado:** contrato de protocolo propuesto; arquitectura de origen de prueba resuelta; formato binario, custodia y frontera privilegiada todavía pendientes.
**Relacionado:** local-pam-bootstrap-authenticator.md, ME-D4O-A-authenticated-domain-bootstrap.md.
**Alcance:** enlazar una reautenticación PAM reciente y una decisión interactiva del operador con una única solicitud de bootstrap LOCAL.

## 1. Principios

1. PAM autentica al sujeto local; no determina el propietario canónico ni autoriza por sí solo la génesis.
2. La confirmación directa ocurre dentro de la frontera confiable del helper, después de mostrar los datos exactos que se autorizarán.
3. La prueba es específica de una solicitud, no delegable, de corta duración, verificable y de un solo uso.
4. El caller Python no puede fabricar retos válidos, resultados PAM, pruebas firmadas ni estados de consumo.
5. El helper no accede a CAM ni a sus bases de datos.
6. La firma demuestra procedencia e integridad de la evidencia, no frescura de la base de datos ni anti-rollback.
7. Un fallo, timeout, reinicio ambiguo o discrepancia deja Recovery Gate cerrado.

## 2. Actores y claves

### 2.1 Helper

El helper C es el emisor de la prueba. Su clave privada de firma, si se mantiene el esquema propuesto, solo será legible por el helper bajo la frontera privilegiada aprobada. No estará en el entorno Python, en el usuario atlas, atlas-sandbox, ni en archivos modificables por esos procesos.

### 2.2 Verificador

El verificador Python posee únicamente la clave pública del emisor. Valida la firma, pero no puede emitir pruebas. La clave pública y el identificador de emisor están fijados en configuración protegida y versionada.

La clave pública no autentica por sí sola que la prueba no haya sido reproducida. El consumo único es una operación separada y atómica.

### 2.3 Solicitud

La invocación interactiva del helper constituye la solicitud. No hay challenge externo, servicio de desafíos ni clave de emisor de desafíos. El helper genera request_id, nonce y proof_id después de validar la configuración protegida y antes de emitir la prueba. CAM verifica el estado pendiente y consume esos identificadores en la UoW de génesis.

## 3. Descriptor protegido y datos de invocación

No existe un challenge firmado ni un emisor separado. El helper lee el descriptor desde configuración protegida del host. El caller no suministra descriptor, action, profile, epoch, sujeto, host, timestamp ni IDs aleatorios.

El descriptor protegido contiene exactamente los campos definidos por `local-bootstrap-coordination-architecture.md` §2 y ME-D4O-A §3. La revisión y el digest de esa configuración se fijan antes de la interacción. Los siguientes valores de la prueba se generan dentro del helper después de validar la configuración:

El descriptor protegido es el definido por `local-bootstrap-coordination-architecture.md` §2 y ME-D4O-A §3. El helper valida su canonicalización, revisión, digest, permisos y correspondencia con el host/sujeto configurados. Los identificadores aleatorios y timestamps de la prueba se generan dentro del helper; ningún campo se recibe como autoridad desde el caller.

El helper verifica la integridad, canonicalización, permisos, sujeto local y host de la configuración. No determina si el bootstrap continúa pendiente: esa condición solo puede decidirla el coordinador CAM dentro de la UoW de génesis.

## 4. Presentación y decisión del operador

El helper no debe limitarse a mostrar un hash opaco. Debe presentar en TTY confiable, con etiquetas inequívocas, como mínimo:

- Que la acción es inicializar el dominio Atlas.
- El identificador del dominio.
- La época inicial.
- El perfil LOCAL.
- El identificador/binding de propietario que se pretende establecer, en forma comprensible y no ambigua.
- El host al que quedará ligado el bootstrap.
- La huella completa del descriptor y la versión de canonicalización.
- Que el perfil LOCAL no ofrece ancla externa ni garantía anti-rollback.

El helper exige una confirmación explícita capturada directamente del TTY. La confirmación debe ser específica del request y no puede provenir de argv, entorno, stdin redirigido, pipe, API de Assistant ni callback Python.

La confirmación humana no se sustituye por pulsar Enter tras un mensaje genérico. La UX exacta (frase de confirmación o comparación de código más confirmación) queda pendiente de prueba de usabilidad, pero el valor debe estar ligado al descriptor mostrado.

Después de confirmar, el helper realiza PAM para el sujeto local configurado. Tanto la decisión directa como la autenticación deben completarse dentro de la misma invocación interactiva. Una sesión previamente autenticada no satisface este requisito.

## 5. Contrato lógico de prueba

Tras validar la configuración protegida, capturar la decisión y completar PAM (incluida la comprobación de cuenta), el helper genera request_id, nonce y proof_id criptográficamente aleatorios y emite una prueba con:

| Campo | Tipo lógico | Regla |
|---|---|---|
| proof_version | entero | Versión admitida |
| issuer_id | ID opaco | Identidad de emisor de helper, fijada en configuración protegida |
| key_id | ID opaco | Clave Ed25519 autorizada, fijada en configuración protegida |
| config_revision | entero/ID opaco | Revisión exacta de configuración protegida |
| config_digest | 32 bytes | SHA-256 de la configuración canónica versionada |
| proof_id | 128 bits | Aleatorio, único |
| request_id | 128 bits | Generado por helper; único dentro del dominio |
| nonce | 256 bits | Coincide con descriptor protegido |
| subject_auth_domain | ID opaco | Host/realm PAM local |
| subject_name | string acotado | Cuenta configurada (greed actualmente) |
| subject_uid | entero | UID observado por helper, no elegido por caller |
| subject_binding_id | ID opaco | Coincide con configuración protegida |
| host_binding_id | ID opaco | Coincide con host configurado |
| action | enum cerrado | DOMAIN_BOOTSTRAP_INITIAL |
| profile | enum cerrado | LOCAL |
| domain_id | ID canónico | Igual al desafío |
| authority_epoch | entero | Igual al desafío |
| descriptor_digest | 32 bytes | Igual al desafío |
| confirmation_commitment | 32 bytes | Igual al desafío |
| pam_service | constante | atlas-bootstrap |
| auth_time | entero UTC | Momento de reautenticación |
| issued_at | entero UTC | Momento de emisión |
| expires_at | entero UTC | Caducidad corta |
| delegation | enum | Siempre NONE |
| signature | bytes | Firma del emisor sobre todos los campos anteriores |

La prueba no contiene contraseña, hash de contraseña, respuesta PAM interna, material secreto ni datos ajenos al bootstrap.

El UID y nombre son atributos observados para auditoría; no constituyen por sí solos el binding ni la identidad canónica. El verificador exige coincidencia con configuración protegida.

## 6. Representación y canonicalización

No se firmará JSON libre ni concatenaciones ambiguas. La representación de transporte debe ser versionada, con tipos y longitudes explícitos, límites estrictos, rechazo de campos duplicados/desconocidos y una única codificación canónica.

**Propuesta para implementación:** envelope binario versionado con enteros de ancho fijo en orden de red, campos de longitud prefijada y enums cerrados. La firma cubre una etiqueta de dominio de separación y todos los bytes canónicos de la prueba, excluyendo únicamente el campo de firma.

El digest del descriptor se calcula sobre la canonicalización versionada que define ME-D4O-A §3. No se crea una segunda canonicalización independiente del descriptor dentro del helper.

**Pendiente antes de código:** fijar layout binario definitivo, límites máximos, endianness, codificación de IDs y vectores de prueba. La estructura debe incluir los campos de configuración/revisión anteriores y usar el mismo digest de descriptor que valida CAM; no se serializará un challenge.

## 7. Algoritmo criptográfico

**Candidato:** Ed25519 para firma y verificación, con OpenSSL EVP en C y la biblioteca cryptography ya declarada en pyproject.toml para el verificador Python.

La disponibilidad de headers y bibliotecas de desarrollo OpenSSL en Debian todavía no se ha comprobado. No instalar paquetes hasta verificar el entorno y aprobar la custodia. Si OpenSSL EVP no está disponible, se revisará una alternativa; no se escribirá criptografía propia.

La clave privada se genera fuera del proceso ordinario Atlas, con permisos y propietario root-only. La rotación y revocación usan key_id, versionado y transición controlada. No se comparte la clave privada entre helper y Python. El identificador de clave y algoritmo se fijan en configuración confiable.

## 8. Verificación y consumo atómico

El verificador realiza, en orden:

1. Parseo estricto y validación de versión/campos.
2. Selección de clave pública por key_id de una lista local confiable; nunca por ruta o URL del payload.
3. Verificación de firma y dominio de separación.
4. Validación de ventana temporal, skew permitido y duración máxima.
5. Comparación exacta con la configuración protegida vigente: revisión/digest, acción, perfil, dominio, época, descriptor, sujeto, host, binding y confirmation commitment.
6. Validación del emisor/key_id autorizados, sujeto local configurado, binding aprobado y estado bootstrap todavía pendiente dentro de la UoW de génesis.
7. Consumo atómico de request_id, nonce y proof_id en la misma UoW que la génesis.
8. Solo después de consumo confirmado, producir un objeto interno de evidencia verificada para la operación de génesis.

El almacenamiento de consumo debe tener restricciones únicas para nonce, request_id y proof_id. La transacción serializa intentos concurrentes: como máximo uno puede consumir la prueba. El consumo, el binding, la identidad, el evento DOMAIN_BOOTSTRAPPED y la proyección Recovery Gate se confirman o revierten juntos. No hay tabla de challenges pendientes ni consumo previo en otra DB. Si hay resultado ambiguo por caída, la idempotencia exacta resuelve el mismo request; cualquier discrepancia mantiene el gate cerrado.

La firma válida sin configuración protegida coincidente, estado de bootstrap pendiente y consumo atómico no es suficiente. Un OwnerDecisionProof interno solo puede construirse por el verificador confiable, nunca mediante deserialización directa desde el caller.

## 9. Caducidad y reloj

La duración máxima de la prueba será corta y configurada. El valor exacto se fijará después de probar la interacción humana y el reloj del host.

- Rechazar timestamps futuros fuera del skew configurado.
- Rechazar issued_at posterior a expires_at.
- Rechazar expiración anterior al momento de verificación.
- Rechazar duración mayor al máximo configurado.
- El reloj no puede ser suministrado por el caller.
- Si la fuente de tiempo no es confiable o hay salto/retroceso incompatible, fallar cerrado.

El reloj de pared sirve para expiración y auditoría, no para impedir replay; el nonce consumido y el estado persistido lo impiden.

## 10. Fallos y recuperación

- Firma inválida, configuración desconocida/alterada, expiración, descriptor distinto, sujeto distinto, TTY no confiable o PAM fallido: no admitir génesis.
- Error de persistencia o consumo: no devolver evidencia verificada.
- Caída tras emisión y antes de la génesis: la prueba solo se admite si sigue vigente y el dominio continúa sin génesis.
- Caída durante la transacción: SQLite revierte consumo y génesis juntos; si el resultado del commit es ambiguo, resolver por request_id y descriptor exactos, sin crear otra identidad.
- Reintento exacto después de commit: devolver el resultado histórico de esa misma operación; reuso para una operación distinta o descriptor distinto: rechazo.
- Descriptor diferente: requiere una nueva solicitud y una nueva decisión interactiva.
- Bootstrap ya completado: rechazo; no hay ruta de rebootstrap por este protocolo.

## 11. Amenazas y límites

Este protocolo reduce falsificación por caller, manipulación de descriptor, repetición y confusión entre autenticación y autorización. No protege frente a root/kernel comprometido, helper reemplazado por root, keylogger, manipulación física del TTY, restauración coherente de datos locales antiguos ni compromiso de clave privada.

El perfil LOCAL acepta explícitamente la limitación anti-rollback descrita por ME-D4O-A. Ed25519, PAM y un nonce no aportan Trust Anchor externo.

## 12. Decisiones que deben cerrarse antes de implementación

1. **Resuelto a nivel de arquitectura:** no existe emisor separado de desafíos ni challenge firmado. El helper C lee el descriptor desde configuración protegida, genera request_id/nonce/proof_id, recoge la decisión y PAM, y emite directamente la prueba firmada; CAM verifica el estado pendiente y consume la prueba junto con la génesis. Siguen pendientes la implementación y las pruebas de esta frontera.
2. Layout binario final y vectores de serialización/canonicalización.
3. Disponibilidad real de OpenSSL EVP headers/libs en Debian.
4. Custodia de clave, key_id, rotación y permisos de helper/configuración.
5. Invocación privilegiada, TTY confiable y captura de confirmación.
6. Persistencia del desafío y consumo único coordinados con la UoW de génesis.
7. Política de expiración y skew del reloj.
8. Binding protegido entre sujeto local greed y la decisión de establecer el propietario canónico, sin derivar UserId del UID.

No se debe comenzar el helper ejecutable hasta cerrar estas decisiones. El siguiente trabajo es cerrar las decisiones restantes de formato binario, custodia de clave, invocación privilegiada/TTY, binding protegido, expiración y coordinación transaccional; después implementar y probar el helper y el coordinador sin duplicar autoridad.
## 13. Inspección de contratos existentes en Atlas (16-11-2026)

La revisión de la rama confirma los siguientes puntos relevantes:

- DM-01 §9.3.4 ya define el contrato lógico de OwnerDecisionProof y OwnerDecisionVerifier para approve/reject/forget de Memory. No existe una implementación de emisor/verificador confiable ni debe reutilizarse ese contrato de Memory como si ya resolviera el bootstrap de dominio.
- SQLiteIdentityAuthority es el único emisor local de los pares canónicos UserId/Identity(USER). Su responsabilidad declarada excluye autenticación, binding externo, recuperación y autorización. Por tanto, el helper PAM no debe llamar a esta autoridad ni generar esos IDs.
- SQLiteIdentityAuthority admite recibir una SQLiteUnitOfWork compartida. Su create_user() puede participar en una transacción mayor si la composición usa exactamente la misma instancia SQLiteDatabase y la misma UoW.
- SQLiteUnitOfWork usa BEGIN IMMEDIATE y controla commit/rollback. Es una primitiva útil para consumo único y génesis local dentro de una transacción común, pero por sí sola no implementa el evento DOMAIN_BOOTSTRAPPED, el verificador de prueba ni el binding del propietario.
- ME-D4O indica que no existe todavía un evento de activación inicial ni una composición completa de la autoridad de recuperación. El dominio nuevo permanece cerrado; no se debe abrir mediante UPDATE manual ni confundir con recuperación vacía.
- El proyecto ya declara cryptography>=42 como dependencia Python. Esto respalda la posibilidad de verificar Ed25519 en Python, pero no confirma la disponibilidad de OpenSSL development headers/libraries para compilar el helper C en Debian.

### Consecuencia de composición

La futura transacción de génesis debe coordinar, en una sola SQLiteUnitOfWork y sobre la misma SQLiteDatabase, al menos: consumo del desafío/prueba, creación canónica UserId/Identity(USER), binding explícito del sujeto local con el propietario canónico, evento de génesis, idempotencia y estado/gate materializado. La transacción no debe aceptar que el caller proporcione una identidad canónica ni un binding ya verificado.

Esta lista es una meta de composición, no una afirmación de que las tablas, puertos o adaptadores de todos esos elementos existan. La inspección actual solo confirma la primitiva UoW y la autoridad de identidad; el modelo persistente de binding y el flujo de génesis siguen pendientes.

### Bloqueadores que permanecen abiertos

1. No existe ni debe añadirse un emisor separado de desafíos. El helper genera los identificadores aleatorios y firma la prueba tras leer la configuración protegida; CAM valida el estado pendiente dentro de la UoW de génesis. La implementación del helper, su configuración protegida y el coordinador CAM siguen pendientes.
2. No existe todavía un binding persistente y verificable entre el sujeto Linux greed y el UserId/Identity(USER) que se creará. No derivar el ID canónico del UID ni del nombre.
3. No existe el evento DOMAIN_BOOTSTRAPPED ni su coordinador transaccional integrado.
4. No está decidido cómo el helper demuestra que su TTY y su invocación privilegiada son confiables.
5. No se han comprobado OpenSSL EVP headers/libs ni la custodia viable de la clave privada en el host.

Por estos bloqueadores, el protocolo queda documentado como diseño propuesto, pero no está listo para implementación del helper. El modelo de emisor/challenge ya quedó resuelto por §14. El binding persistente del propietario, el layout binario, la custodia de clave, la invocación/TTY y la coordinación transaccional siguen pendientes antes de implementar el helper.

## 14. Resolución de arquitectura: sin emisor de desafíos separado

La propuesta anterior de §§2.3 y 3 de este documento queda **sustituida** por la arquitectura de [coordinación del bootstrap LOCAL](local-bootstrap-coordination-architecture.md), que es la referencia vigente para el origen de la solicitud y el descriptor.

No habrá un servicio separado que firme desafíos. El helper no recibirá un descriptor ni un challenge fabricado por Python. En su lugar, leerá el descriptor esperado desde configuración protegida del host, presentará esos términos al operador, recogerá la confirmación en su TTY, realizará PAM y generará internamente request_id, nonce y proof_id. La prueba firmada enlazará el digest/revisión de esa configuración y todos los atributos observados.

La configuración protegida define qué bootstrap está permitido solicitar; no demuestra que siga pendiente. El verificador CAM debe comprobar el estado pendiente dentro de la transacción de génesis. La prueba firmada no abre el gate por sí misma.

El consumo único de proof_id/request_id/nonce y el evento DOMAIN_BOOTSTRAPPED deben confirmarse en la misma SQLiteUnitOfWork que la creación de identidad y binding. Un fallo revierte todo; un commit ambiguo se resuelve por idempotencia exacta, no emitiendo una segunda identidad.

El bootstrap_binding_id es un slot de propietario estable configurado, no un UserId. SQLiteIdentityAuthority genera el UserId canónico durante la transacción; el binding hacia ese UserId se registra en la misma UoW.

El resto del contrato de firma, expiración, validación estricta, TTY, PAM, replay y límites sigue vigente en cuanto no contradiga esta resolución. El layout binario, la invocación privilegiada, la custodia de clave y los límites temporales siguen pendientes.
