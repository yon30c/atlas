# Protocolo de prueba para autenticación y decisión directa del bootstrap LOCAL

**Estado:** contrato de protocolo propuesto; pendiente de revisión antes de implementar.
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

### 2.3 Solicitud y desafío

La solicitud de bootstrap debe originarse en un coordinador confiable y en estado de bootstrap pendiente. Antes de permitir la autenticación, el helper comprueba que el desafío procede de un emisor autorizado, que está ligado al descriptor exacto y que no ha expirado.

**Decisión pendiente:** arquitectura concreta del emisor de desafíos y su clave. No se acepta que Assistant firme desafíos, que el caller invente un desafío válido o que el helper firme ciegamente bytes proporcionados por el caller. El emisor debe consultar/validar el estado protegido de bootstrap pendiente y solo emitir desafíos para la única operación inicial LOCAL permitida.

## 3. Contrato lógico de desafío

El desafío autenticado contiene exactamente:

| Campo | Tipo lógico | Regla |
|---|---|---|
| protocol_version | entero | Versión admitida explícitamente |
| issuer_id | ID opaco | Emisor de desafío confiable |
| request_id | 128 bits | Aleatorio, único, no reutilizado |
| nonce | 256 bits | Aleatorio criptográficamente |
| issued_at | entero UTC | Emitido por fuente confiable |
| expires_at | entero UTC | Ventana corta, límite configurado |
| action | enum cerrado | Solo DOMAIN_BOOTSTRAP_INITIAL |
| profile | enum cerrado | Solo LOCAL |
| domain_id | ID canónico | Dominio exacto |
| authority_epoch | entero | Época inicial exacta |
| descriptor_digest | 32 bytes | SHA-256 del descriptor canónico versionado |
| subject_binding_id | ID opaco | Binding local protegido esperado |
| host_binding_id | ID opaco | Host local esperado |
| confirmation_commitment | 32 bytes | Compromiso de los términos mostrados y confirmados |

El desafío se autentica mediante un mecanismo que el helper verifica sin compartir con el caller la clave privada del emisor. Campos desconocidos, duplicados, omitidos, fuera de rango o no canónicos se rechazan.

El helper verifica que el desafío está destinado al host y sujeto configurados, corresponde a un bootstrap inicial aún pendiente y que no existe ya un dominio activo o una génesis previa. La autoridad de ese estado debe ser una fuente protegida independiente del caller.

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

Tras verificar el desafío, capturar la decisión y completar PAM (incluida la comprobación de cuenta), el helper emite una prueba con:

| Campo | Tipo lógico | Regla |
|---|---|---|
| proof_version | entero | Versión admitida |
| issuer_id | ID opaco | Identidad de emisor de helper |
| proof_id | 128 bits | Aleatorio, único |
| request_id | 128 bits | Igual al desafío |
| nonce | 256 bits | Igual al desafío |
| subject_auth_domain | ID opaco | Host/realm PAM local |
| subject_name | string acotado | Cuenta configurada (greed actualmente) |
| subject_uid | entero | UID observado por helper, no elegido por caller |
| subject_binding_id | ID opaco | Igual al desafío y configuración protegida |
| host_binding_id | ID opaco | Igual al desafío y host configurado |
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

**Pendiente antes de código:** fijar layout binario definitivo, límites máximos, endianness, codificación de IDs y vectores de prueba.

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
5. Comparación exacta con el desafío pendiente: request_id, nonce, acción, perfil, dominio, época, digest, sujeto, host y confirmation commitment.
6. Validación de emisor, sujeto local configurado, binding aprobado y estado bootstrap todavía pendiente.
7. Consumo atómico de request_id, nonce y proof_id en la autoridad protegida.
8. Solo después de consumo confirmado, producir un objeto interno de evidencia verificada para la operación de génesis.

El almacenamiento de consumo debe tener restricciones únicas para nonce, request_id y proof_id. La transacción serializa intentos concurrentes: como máximo uno puede consumir la prueba. El consumo y la admisión a génesis deben coordinarse según el protocolo de bootstrap y su UoW; no se confirma consumo en una DB distinta y se asume que la génesis ocurrió. Si hay resultado ambiguo por caída, el estado queda bloqueado y requiere reconciliación explícita.

La firma válida sin registro de desafío pendiente y sin consumo atómico no es suficiente. Un OwnerDecisionProof interno solo puede construirse por el verificador confiable, nunca mediante deserialización directa desde el caller.

## 9. Caducidad y reloj

La duración máxima de desafío y prueba será corta y configurada. El valor exacto se fijará después de probar la interacción humana y el reloj del host.

- Rechazar timestamps futuros fuera del skew configurado.
- Rechazar issued_at posterior a expires_at.
- Rechazar expiración anterior al momento de verificación.
- Rechazar duración mayor al máximo configurado.
- El reloj no puede ser suministrado por el caller.
- Si la fuente de tiempo no es confiable o hay salto/retroceso incompatible, fallar cerrado.

El reloj de pared sirve para expiración y auditoría, no para impedir replay; el nonce consumido y el estado persistido lo impiden.

## 10. Fallos y recuperación

- Firma inválida, challenge desconocido, expiración, descriptor distinto, sujeto distinto, TTY no confiable o PAM fallido: no emitir prueba.
- Error de persistencia o consumo: no devolver evidencia verificada.
- Caída tras emisión pero antes del consumo: la prueba puede verificarse solo mientras el desafío siga pendiente y no expirado.
- Caída durante consumo: resolver mediante transacción durable; resultado ambiguo mantiene Recovery Gate cerrado.
- Reintento de la misma prueba: rechazo como ya consumida.
- Descriptor diferente: requiere una nueva solicitud y una nueva decisión interactiva.
- Bootstrap ya completado: rechazo; no hay ruta de rebootstrap por este protocolo.

## 11. Amenazas y límites

Este protocolo reduce falsificación por caller, manipulación de descriptor, repetición y confusión entre autenticación y autorización. No protege frente a root/kernel comprometido, helper reemplazado por root, keylogger, manipulación física del TTY, restauración coherente de datos locales antiguos ni compromiso de clave privada.

El perfil LOCAL acepta explícitamente la limitación anti-rollback descrita por ME-D4O-A. Ed25519, PAM y un nonce no aportan Trust Anchor externo.

## 12. Decisiones que deben cerrarse antes de implementación

1. Identidad y frontera del emisor de desafíos, incluido cómo consulta el bootstrap pendiente sin confiar en Assistant.
2. Layout binario final y vectores de serialización/canonicalización.
3. Disponibilidad real de OpenSSL EVP headers/libs en Debian.
4. Custodia de clave, key_id, rotación y permisos de helper/configuración.
5. Invocación privilegiada, TTY confiable y captura de confirmación.
6. Persistencia del desafío y consumo único coordinados con la UoW de génesis.
7. Política de expiración y skew del reloj.
8. Binding protegido entre sujeto local greed y la decisión de establecer el propietario canónico, sin derivar UserId del UID.

No se debe comenzar el helper ejecutable hasta cerrar estas decisiones. El siguiente trabajo es inspeccionar los contratos y primitivas existentes en Atlas para determinar si el verificador y el consumo pueden componerse sin duplicar autoridad ni crear una segunda fuente de verdad.