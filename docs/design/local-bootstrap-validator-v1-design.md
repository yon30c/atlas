# Diseño V1 del validador aislado de bootstrap LOCAL

**Estado:** propuesta de diseño para revisión; no implementada ni aprobada para ejecución privilegiada.  
**Rama objetivo:** `feature/terminal-commands`.  
**Fecha:** 16 de noviembre de 2026.  
**Relacionado:** `local-bootstrap-privilege-validation-contract.md`, `local-bootstrap-privilege-boundary.md`, `tools/bootstrap-probe/README.md`.

## 1. Objetivo y alcance

V1 prepara una base verificable para probar el parseo y la consistencia de observaciones de procesos Linux. Debe ser independiente del probe diagnóstico existente y ejecutarse exclusivamente como programa de pruebas sin privilegios.

V1 no valida una invocación real de bootstrap, no autentica al operador, no demuestra procedencia de TTY y no decide que el candidato A sea seguro.

**Regla central:** ningún resultado de V1 equivale a autorización. El componente no tendrá una decisión pública `ALLOW`, no emitirá proof, no tendrá acceso a claves, PAM, configuración protegida, SQLite o CAM.

## 2. Separación de componentes

Mantener dos árboles independientes:

- `tools/bootstrap-probe/`: observador diagnóstico actual. No se convierte en biblioteca ni se enlaza al validador.
- `tools/bootstrap-validator/`: parsers puros, modelos de observación, comprobaciones de consistencia y harness de pruebas V1.

V1 no reutilizará funciones del probe. El código de producción potencial y los fixtures de pruebas no compartirán un ejecutable.

## 3. Arquitectura propuesta

### 3.1 Capa de parseo pura

Funciones que reciben bytes y longitud explícita; no abren archivos, no consultan procfs y no dependen de variables globales.

- Parser de campos seleccionados de `/proc/<pid>/status`.
- Parser de `/proc/<pid>/stat`, incluyendo `starttime`.
- Conversión decimal estricta con comprobación de overflow y rango.
- Tipos de resultado diferenciados: correcto, entrada inválida, entrada truncada y campo requerido ausente/duplicado.

Los parsers no realizan llamadas al sistema ni deciden autoridad.

### 3.2 Modelo normalizado

Representar los datos parseados en estructuras explícitas y sin punteros a buffers temporales:

- Identidad de proceso: PID, PPID, UID/GID real, efectivo, saved y filesystem.
- Estado de proceso: estado, PGID, SID, TTY number, foreground TPGID y starttime.
- Estado de referencia pidfd: no solicitado, abierto/no señalado, terminado o error.
- Datos de TTY: SID, foreground PGID, PGID observado y metadatos del dispositivo, solo como observaciones.

Los valores ausentes o no verificables deben representarse como tales; nunca inicializarlos a cero y tratarlos como datos reales.

### 3.3 Evaluador de consistencia pura

Recibe un snapshot construido por el caller y una política de prueba explícita. Solo puede producir:

- `OBSERVATION_CONSISTENT`: las observaciones presentes no se contradicen según las reglas limitadas de V1.
- `OBSERVATION_INCONSISTENT`: hay una contradicción verificable.
- `OBSERVATION_INCOMPLETE`: falta un dato requerido o no pudo verificarse.

El nombre y la documentación deben dejar claro que `OBSERVATION_CONSISTENT` no significa identidad autenticada, invocación confiable, autorización ni aprobación del candidato A. El evaluador no tendrá una salida `AUTHORIZED` o `PROOF_READY`.

## 4. Contrato de parseo

### 4.1 Reglas generales

- Entrada como `const unsigned char *` más longitud; nunca asumir que existe terminador NUL.
- Límites máximos explícitos por formato.
- Rechazar buffer vacío, truncado, excesivo o con NUL embebido.
- No asumir que una sola lectura de archivo siempre devuelve el contenido completo; el futuro lector deberá acumular hasta EOF dentro del límite.
- Parsear números en base 10, aceptar solo la gramática prevista y comprobar overflow antes de convertir.
- Exigir exactamente los campos requeridos y detectar duplicados.
- No usar `sscanf` como parser contractual: sus conversiones permisivas no garantizan consumo completo ni detección clara de overflow.
- Errores de parseo no deben dejar estructuras parcialmente válidas utilizables por el evaluador.

### 4.2 `/proc/<pid>/status`

Extraer como mínimo `PPid`, `Uid` y `Gid`.

- Cada campo requerido debe aparecer exactamente una vez.
- `Uid` y `Gid` deben contener exactamente cuatro valores decimales dentro del rango del tipo de destino.
- `PPid` debe ser un entero decimal no negativo y estar dentro del rango de PID soportado.
- Campos desconocidos se ignoran después de validar que la línea está dentro del límite.
- Campos requeridos malformados, duplicados o ausentes invalidan el documento completo.

### 4.3 `/proc/<pid>/stat`

El parser debe validar el PID inicial y separar el campo `comm` entre paréntesis sin asumir que su contenido carece de espacios o paréntesis. Después debe tokenizar los campos desde `state` (campo 3) hasta `starttime` (campo 22), verificando la cantidad, gramática y rango de cada campo utilizado.

Campos mínimos:

- 3: state
- 4: ppid
- 5: pgrp
- 6: session
- 7: tty_nr
- 8: tpgid
- 22: starttime

No aceptar una línea si faltan campos hasta 22, si el PID no coincide con el solicitado, si hay overflow o si quedan tokens inesperados incompatibles con el formato. El parser no inferirá procedencia del TTY a partir de `tty_nr`.

## 5. Reglas limitadas del evaluador V1

V1 puede comprobar coherencia entre datos sintéticos o capturados por fixtures:

1. PID solicitado, PID del registro y PID del snapshot deben coincidir.
2. PPID del helper capturado y PID del padre observado deben coincidir.
3. PPID de `status` y `stat` del mismo padre deben coincidir.
4. starttime debe estar presente y ser idéntico en las observaciones repetidas del mismo registro de prueba.
5. Una referencia pidfd marcada como terminada o con error no puede clasificarse como consistente.
6. UID/GID deben estar completos; el evaluador puede comparar los valores contra una política de fixture explícita, nunca derivada del modelo ni de variables de entorno.
7. Las contradicciones entre SID, PGID, TTY y foreground pueden marcarse como inconsistentes cuando las relaciones concretas estén expresamente definidas en el fixture.

No forman parte de una decisión de confianza en V1:

- aceptar un nombre o ruta de ejecutable como identidad de sudo;
- decidir que un padre es sudo por su nombre, ruta o inode aislado;
- aceptar ancestros indirectos;
- inferir si el PTY procede de SSH o de `sudo use_pty`;
- demostrar atomicidad de parentesco, credenciales o `execve`;
- aceptar una sesión como bootstrap autenticado.

Las condiciones aún no demostradas del contrato principal permanecen abiertas. En particular, V1 no resuelve la distinción entre SSH con PTY y SSH sin PTY cuando sudo puede crear un PTY interno.

## 6. Interfaz de observación y pruebas

La primera versión no tendrá un recolector real de procesos. El harness construirá snapshots desde fixtures controlados y llamará a parsers/evaluador puros.

Si más adelante se propone un recolector Linux, será un componente separado y requerirá revisión específica de carreras, pidfd, procfs, TTY y procedencia. No se añadirá implícitamente a V1.

Los fixtures deben poder representar:
- observación completa y coherente;
- campo ausente, duplicado, malformado o truncado;
- PID/PPID/starttime contradictorios;
- credenciales inesperadas;
- pidfd terminado o no verificable;
- SID/PGID/TTY/foreground incompatibles;
- lecturas que fallan o cambian entre muestras.

## 7. Matriz mínima de pruebas V1

### Parser de status

- orden distinto de campos;
- campos desconocidos intercalados;
- LF y última línea sin LF;
- cada campo requerido ausente;
- duplicados de `PPid`, `Uid` y `Gid`;
- valores negativos, signos, texto adicional y overflow;
- número incorrecto de UID/GID;
- buffer vacío, NUL embebido, truncado y superior al límite.

### Parser de stat

- `comm` con espacios;
- `comm` con paréntesis internos;
- PID inicial distinto del solicitado;
- falta de cada campo requerido, especialmente campo 22;
- campos numéricos inválidos, negativos donde no proceda y overflow;
- línea truncada, vacía, excesiva o con tokens adicionales;
- estado inválido y separadores incorrectos.

### Evaluador

- snapshot coherente de referencia;
- PID y PPID no coincidentes;
- PPID status/stat contradictorios;
- starttime diferente entre muestras;
- UID/GID incompletos o distintos de la política de fixture;
- pidfd terminado/error;
- TTY/foreground/SID contradictorios;
- cualquier dato obligatorio ausente produce `OBSERVATION_INCOMPLETE`;
- toda contradicción produce `OBSERVATION_INCONSISTENT`;
- ningún caso produce autorización ni bytes de prueba.

Cada prueba negativa debe comprobar el resultado exacto y que no existe ruta de emisión de proof.

## 8. Construcción y límites operativos

- C estándar compatible con el toolchain Debian del proyecto.
- Compilación estricta con `-std=c11 -Wall -Wextra -Wpedantic -Werror`.
- Sin dependencias externas nuevas.
- Ejecutables y fixtures solo dentro del checkout o `/tmp`; nunca bajo `/usr`, `/usr/local` o rutas privilegiadas.
- No setuid ni file capabilities.
- No sudo, PAM, systemd, Broker, SQLite, CAM, red, claves ni archivos de configuración del host.
- No instalar paquetes ni modificar el host.

Las pruebas con sanitizers pueden ejecutarse si el compilador ya los soporta; no se instalarán herramientas para habilitarlos.

## 9. Criterios de cierre V1

V1 se considera completo únicamente cuando:

1. parsers puros implementados con límites y errores estrictos;
2. matriz mínima de pruebas automatizada;
3. evaluación pura con solo los tres estados no autoritativos definidos;
4. pruebas negativas demuestran rechazo o indeterminación fail-closed;
5. build estricto y suite V1 pasan en Debian;
6. revisión confirma que no hay dependencia ni enlace con el probe diagnóstico;
7. README y contrato principal reflejan el alcance real.

Cerrar V1 no aprueba A, no autoriza PAM ni helper privilegiado y no resuelve la procedencia de TTY. Después de V1 se decidirá si existe una vía técnicamente defendible para un recolector de observaciones V2 o si corresponde descartar A y reabrir el diseño de B.

## 10. Decisión solicitada

Revisar y aprobar este alcance V1 antes de escribir código. La aprobación de V1 autorizaría únicamente un parser/evaluador aislado y pruebas sin privilegios; no autorizaría integración con el sistema real ni cambios de host.
