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

1. **Bootstrap coordinator:** crea una solicitud con request_id y descriptor canónico; no puede declarar autenticación exitosa.
2. **Helper C privilegiado y mínimo:** valida el contexto de invocación, muestra el descriptor exacto en un TTY confiable, solicita reautenticación PAM del sujeto configurado y produce una prueba limitada a esa solicitud.
3. **PAM service `atlas-bootstrap`:** aplica autenticación Unix y comprobaciones de cuenta usando módulos del sistema. La política de fallos pertenece exclusivamente a este servicio.
4. **Proof verifier/consumer:** valida emisor, sujeto, acción, descriptor, request_id, expiración y nonce; consume la prueba de forma atómica y de un solo uso.
5. **CAM bootstrap:** después de verificar la prueba y la decisión explícita del propietario, genera la identidad canónica y aplica génesis conforme a ME-D4O-A. El helper no accede a SQLite CAM.

La prueba no debe ser un JSON autocertificado ni un objeto Python que el caller pueda construir como `VERIFIED`. El emisor debe autenticarse criptográficamente o mediante un canal local autenticado cuya frontera y permisos estén demostrados.

## 4. Flujo previsto

1. El coordinador obtiene el descriptor canónico y crea un request_id impredecible.
2. El helper recibe la solicitud por un canal definido y comprueba que corresponde al único tipo de operación permitido: bootstrap LOCAL inicial.
3. El helper verifica que el proceso invocador y el TTY satisfacen la política local protegida. No confía en nombre de usuario, UID, variables de entorno ni argumentos aislados como prueba suficiente.
4. El helper muestra al operador el dominio, época, perfil, identidad/binding que se pretende establecer y commitment exacto. La confirmación se captura directamente en el helper.
5. PAM autentica al sujeto configurado y comprueba el estado de la cuenta. La contraseña se solicita por conversación PAM; nunca se recibe por argv, variables de entorno, archivo, stdin redirigido o log.
6. El helper emite una prueba temporal que enlaza request_id, nonce, sujeto cualificado por host/dominio de autenticación, acción y digest del descriptor exacto.
7. El verificador comprueba la autenticidad de la prueba, su vigencia y todos los vínculos, y consume nonce/request_id de forma atómica. Repetición, expiración, mismatch o emisor desconocido se rechazan.
8. Solo entonces el flujo de bootstrap puede presentar la evidencia de autenticación y la decisión directa del propietario al componente CAM. La creación canónica de UserId/Identity(USER), evento de génesis y estado asociado permanece dentro de la autoridad/UoW prevista.

La autenticación PAM prueba la posesión de la credencial local en ese momento. No prueba por sí sola la decisión directa sobre el descriptor; esa decisión requiere confirmación independiente, mostrada y capturada por la frontera confiable.

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

## 9. Estado actual

**Aprobado:** helper C separado con libpam como proveedor local candidato; cuenta operativa inicial `greed`; servicio PAM exclusivo; no modificar PAM global.

**No implementado:** código C, archivo PAM, configuración protegida, clave, protocolo de prueba, verificador, consumo, binding canónico, bootstrap CAM.

**No autorizado por esta decisión:** instalar paquetes, crear/modificar archivos en `/etc`, habilitar servicios, crear usuarios/identidades/Grants, inicializar CAM, abrir Recovery Gate o conectar runtime.

La implementación se realizará por entregas pequeñas: primero cerrar el protocolo y la frontera de privilegios; después helper y pruebas unitarias; finalmente integración PAM aislada y pruebas de integración en el host, con instalación manual aprobada.
