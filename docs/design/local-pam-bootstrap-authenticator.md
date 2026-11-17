# Diseño del autenticador PAM local para bootstrap

**Estado:** diseño inicial aprobado; implementación pendiente.  
**Rama:** `feature/terminal-commands`.  
**Decisión:** helper C separado con `libpam`, aprobado el 16 de noviembre de 2026.  
**Alcance:** autenticación reciente del operador local para el bootstrap LOCAL de CAM.

## 1. Objetivo y no objetivos

El helper proporciona evidencia de que el sujeto local aprobado se reautenticó recientemente mediante PAM para una solicitud concreta de bootstrap.

No es:
- una autoridad CAM;
- un gestor de identidades o Grants;
- un proceso de Assistant;
- un mecanismo de recuperación de cuenta;
- una autorización general para ejecutar operaciones;
- un Trust Anchor externo ni una garantía anti-rollback.

La cuenta `greed` es el sujeto operativo inicial aprobado en el host actual. La cuenta técnica `atlas` y la cuenta de servicio `atlas-sandbox` no son propietarios.

## Política de terminal: local y SSH con PTY

Se admite tanto un terminal local como una sesión SSH interactiva con PTY. SSH sin PTY y cualquier invocación no interactiva se rechazan. Un PTY válido demuestra una sesión de terminal interactiva, no presencia física ante el servidor.

La confirmación del descriptor se captura directamente del TTY controlador validado; nunca de stdin, argumentos, entorno, pipes ni callbacks. PAM debe autenticar nuevamente al sujeto configurado y aprobar `pam_acct_mgmt`; una sesión SSH ya autenticada o la caché de sudo no sustituyen esta reautenticación. La pérdida de TTY, foreground o sesión cancela el flujo sin emitir prueba. Los detalles y pruebas negativas están en [Frontera de privilegios del bootstrap LOCAL](local-bootstrap-privilege-boundary.md).

## 2. Datos de entorno confirmados

- Debian con PAM `1.7.0-5`.
- `libpam0g`, `libpam-modules`, `libpam-modules-bin` y `libpam-runtime` instalados.
- `pam_unix.so` y `pam_faillock.so` disponibles desde `libpam-modules`.
- `libpam.so.0` y `libpam_misc.so.0` disponibles.
- El stack común actual usa `pam_unix.so`; no debe modificarse para esta integración.
- La cuenta `greed` está activa y tiene contraseña configurada.
- No existe todavía un servicio PAM `atlas-bootstrap`.
- El módulo `pam_faillock.so` no está integrado en el stack común observado. Su presencia en disco no demuestra que el host aplique lockout.
- No se ha instalado `pamtester`; no es requisito de runtime.

Estos datos describen el diagnóstico del host, no una prueba de funcionamiento del futuro servicio.

## 3. Componentes y límites de confianza

1. **Configuración protegida del host:** declara el descriptor exacto, sujeto local, binding slot, perfil y clave pública/emisor permitidos. No es modificable por Assistant ni por procesos Atlas ordinarios.
2. **Helper C/libpam:** lee esa configuración por ruta fija, valida host/sujeto/TTY, presenta el descriptor, recoge confirmación directa, ejecuta PAM y emite una prueba firmada. No recibe del caller los campos que definen la operación.
3. **PAM service `atlas-bootstrap`:** aplica autenticación Unix y comprobaciones de cuenta con módulos del sistema. La política de fallos pertenece exclusivamente a este servicio.
4. **Proof verifier/consumer:** valida la firma y todos los vínculos, y consume la prueba dentro de la misma UoW que la génesis.
5. **CAM bootstrap:** verifica que el dominio sigue pendiente, genera identidad canónica, persiste binding y evento de génesis y actualiza gate en una transacción.

La arquitectura de coordinación vigente está en [local-bootstrap-coordination-architecture.md](local-bootstrap-coordination-architecture.md). La frontera de privilegios e invocación se define en [local-bootstrap-privilege-boundary.md](local-bootstrap-privilege-boundary.md).

La prueba no es un JSON autocertificado ni un objeto Python que el caller pueda construir como VERIFIED. La clave privada está reservada al helper; Python solo posee la clave pública. El estado pendiente y el consumo único se comprueban en CAM.

## 4. Flujo previsto

1. Un operador inicia explícitamente el procedimiento local.
2. El mecanismo privilegiado ejecuta el helper sin argumentos y con acceso al TTY confiable.
3. El helper lee y valida el descriptor desde configuración protegida del host; no recibe descriptor ni acción desde Python.
4. El helper presenta el dominio, época, perfil LOCAL, slot de propietario y huella/revisión del descriptor.
5. El operador confirma directamente en el TTY del helper.
6. El helper ejecuta `pam_start`, `pam_authenticate` y `pam_acct_mgmt` para el sujeto local configurado.
7. El helper genera request_id, nonce y proof_id, firma la prueba ligada al descriptor/configuración y sujeto observados y la entrega por el canal de salida definido.
8. El coordinador CAM verifica firma y campos, comprueba que no existe génesis previa y consume la prueba, crea UserId/Identity(USER), persiste el binding, registra DOMAIN_BOOTSTRAPPED y actualiza head/gate en una única SQLiteUnitOfWork.
9. Una verificación posterior independiente comprueba evento, firma, descriptor, binding, head y gate antes de habilitar operaciones.

PAM prueba autenticación reciente del sujeto configurado. La confirmación TTY prueba la decisión directa sobre los términos mostrados. Ninguna de las dos, aislada, abre el gate.

## 5. Requisitos del servicio PAM dedicado

El archivo futuro `/etc/pam.d/atlas-bootstrap` será independiente. El stack debe:

- limitar el servicio al usuario local configurado para bootstrap;
- realizar autenticación con `pam_unix.so`;
- ejecutar comprobación de cuenta con la pila `account`;
- aplicar control de intentos fallidos exclusivamente en este servicio;
- evitar sesiones PAM innecesarias y no abrir sesiones de login;
- denegar si faltan módulos requeridos o la configuración no es válida;
- no incluir `common-auth` por defecto, para evitar heredar cambios generales no revisados;
- no modificar los archivos PAM existentes.

El orden y los controles exactos de `pam_faillock` (preauth/authfail/authsucc), los valores de deny/fail_interval/unlock_time y el comportamiento ante errores deben revisarse con la documentación de la versión instalada y pruebas en entorno aislado antes de habilitar el servicio. No se fijan umbrales por inferencia.

## 6. Seguridad del helper C

- Código pequeño, sin shell-outs y sin ejecutar comandos del usuario.
- Sin setuid implícito: el mecanismo de invocación privilegiada debe seleccionarse y justificarse antes de implementar o instalar.
- No aceptar nombres de usuario, rutas de configuración, claves, módulos PAM ni políticas elegidas libremente por el caller.
- Configuración y clave de emisión, si se utiliza, bajo directorios root-owned, no modificables por Assistant ni por el usuario de servicio.
- Sin secretos en argv, entorno, logs, stdout/stderr o archivos temporales.
- Interacción sensible únicamente mediante TTY validado; rechazar pipes y sesiones no interactivas.
- Validar tamaños, codificación, canonicalización y campos exactos del descriptor.
- Limitar el helper a una acción de bootstrap inicial y al perfil LOCAL; rechazar otras operaciones y cualquier rebootstrap.
- Prueba firmada con clave privada inaccesible al proceso ordinario Atlas; el verificador usa clave pública. La elección concreta de formato, biblioteca y rotación está pendiente.
- El nonce se consume en almacenamiento de autoridad protegido; firma válida no equivale a prueba no reutilizada.
- No devolver datos internos PAM ni distinguir detalles que faciliten enumeración de cuentas.
- Fallar cerrado ante cualquier error.

## 7. Decisiones técnicas pendientes antes de codificar

1. **Invocación privilegiada:** seleccionar una mediación concreta (por ejemplo, comando root-owned invocado mediante una regla administrativa explícita) sin introducir un setuid genérico. Verificar TTY, UID real, UID efectivo y procedencia de invocación; documentar qué amenazas quedan fuera del modelo.
2. **Protocolo:** definir solicitud binaria/canónica, nonce, request_id, digest del descriptor y respuesta de prueba. No firmar bytes ambiguos ni JSON no canonicalizado.
3. **Criptografía:** elegir algoritmo y biblioteca ya disponible o dependencia explícita; proteger clave privada y publicar solo clave verificadora.
4. **Binding:** formalizar la configuración protegida que permite al sujeto autenticado actuar como operador del bootstrap que establece al propietario canónico. No derivar UserId de `greed` ni del UID.
5. **Consumo:** definir cómo el verificador rechaza replay y consume evidencia con atomicidad, incluyendo reinicio y concurrencia.
6. **PAM policy:** definir política de lockout dedicada, comportamiento account, TTY y mensajes sin cambiar el stack del sistema.
7. **Instalación/actualización:** definir propietario, grupo, modos, directorios, integridad del binario y rotación/revocación de clave.

No se debe escribir el helper ejecutable hasta cerrar estos puntos. En particular, no se debe emitir una prueba firmada antes de que el emisor pueda verificar por sí mismo el request exacto y capturar la decisión directa del propietario.

## 8. Pruebas requeridas

### PAM y entrada
- credencial correcta/incorrecta;
- cuenta bloqueada, expirada o no autorizada;
- servicio PAM ausente o módulo faltante;
- ausencia de TTY, stdin redirigido, terminal no confiable;
- usuario distinto de `greed`;
- intentos fallidos, umbral, ventana y desbloqueo conforme a política;
- comprobar que no se afecta login, SSH, sudo ni otras aplicaciones PAM.

### Prueba y verificador
- firma válida y descriptor exacto;
- firma alterada, clave desconocida y payload no canónico;
- request_id/nonce incorrectos, expirados o ya consumidos;
- replay concurrente: exactamente un consumo puede tener éxito;
- sujeto/host, acción, dominio, época, perfil o commitment distintos;
- proceso caller intenta inventar estado de éxito o escoger otro sujeto;
- reinicio entre emisión y consumo;
- error de persistencia: no confirmar consumo parcial ni abrir CAM.

### Límites CAM
- prueba PAM válida sin confirmación directa no inicializa CAM;
- confirmación sin prueba PAM válida no inicializa CAM;
- helper nunca crea identidad, Grants, binding ni evento de génesis;
- UserId/Identity(USER) se generan mediante Identity Authority;
- rebootstrap y descriptor distinto se rechazan;
- cualquier fallo deja Recovery Gate cerrado.

## 8.1 Protocolo de desafío y prueba

El contrato detallado de desafío autenticado, presentación del descriptor, confirmación directa, prueba firmada, verificación y consumo atómico está en [Protocolo de prueba para bootstrap LOCAL](local-pam-bootstrap-proof-protocol.md). Ese documento es una propuesta contractual; sus decisiones pendientes deben cerrarse antes de escribir el helper ejecutable.

## 9. Estado actual

**Aprobado:** helper C separado con libpam como proveedor local candidato; cuenta operativa inicial `greed`; servicio PAM exclusivo; no modificar PAM global.

**No implementado:** código C, archivo PAM, configuración protegida, clave, protocolo de prueba, verificador, consumo, binding canónico, bootstrap CAM.

**No autorizado por esta decisión:** instalar paquetes, crear/modificar archivos en `/etc`, habilitar servicios, crear usuarios/identidades/Grants, inicializar CAM, abrir Recovery Gate o conectar runtime.

La implementación se realizará por entregas pequeñas: primero cerrar el protocolo y la frontera de privilegios; después helper y pruebas unitarias; finalmente integración PAM aislada y pruebas de integración en el host, con instalación manual aprobada.


## 10. Arquitectura de coordinación vigente

El flujo y la frontera de confianza quedan detallados en [Arquitectura de coordinación del bootstrap LOCAL](local-bootstrap-coordination-architecture.md). Esta arquitectura sustituye el coordinador emisor de desafíos separado descrito en las primeras secciones de este documento: el helper lee el descriptor de configuración protegida del host, genera request_id/nonce/proof_id por sí mismo y firma la prueba después de la confirmación directa y PAM. No acepta del caller los campos que definen la operación.

La configuración protegida declara el bootstrap permitido, pero CAM comprueba que siga pendiente dentro de la misma UoW que consume la prueba y registra la génesis. El helper nunca consulta SQLite/CAM. El binding se realiza mediante bootstrap_binding_id y la autoridad de identidad genera el UserId canónico durante la transacción. No se reutiliza OwnerDecisionVerifier de Memory para el bootstrap.
