# Atlas Desktop para Windows — decisiones aprobadas

> Estado: decisiones de producto y arquitectura aprobadas; **no equivalen a implementación**.
> Registro: 15 de noviembre de 2026.
> Alcance: cliente de escritorio inicial de Atlas Assistant para Windows.

Este documento conserva las decisiones acordadas para que el desarrollo de Desktop no las reinterprete ni las convierta accidentalmente en funcionalidades ya existentes. Cuando una capacidad no esté implementada, debe seguir identificándose como pendiente.

## 1. Decisiones aprobadas

| Área | Decisión |
|---|---|
| Aplicación de escritorio | C# + .NET + WinUI 3 |
| Plataforma inicial | Windows |
| Comunicación | API remota de Atlas Assistant |
| Acceso de red | Tailscale VPN existente |
| Transporte seguro | HTTPS/TLS |
| Autenticación | Vinculación explícita de dispositivos, independiente de Tailscale |
| Credenciales | Específicas por dispositivo, revocables y almacenadas de forma segura |
| Audio | Piper TTS, por el momento; elección provisional |
| Motor descartado | Phonon |

La selección de Piper es provisional. **No significa que Piper esté instalado, configurado, expuesto mediante la API ni integrado con Desktop.** Phonon queda descartado para este plan.

## 2. Áreas principales de la interfaz inicial

La aplicación tendrá cuatro áreas principales:

1. **Chat:** conversación con Atlas Assistant y recepción progresiva de respuestas.
2. **Conversaciones:** acceso a conversaciones anteriores.
3. **Conexión:** estado de conexión con el servidor y proceso de vinculación del dispositivo.
4. **Configuración:** preferencias de la aplicación.

La primera etapa de interfaz será exclusivamente de texto. No incluirá reconocimiento de voz ni controles de micrófono.

No se han aprobado todavía decisiones visuales detalladas. No asumir colores, tipografía, iconografía, disposición final, tema ni diseño de componentes sin una decisión posterior.

## 3. Arquitectura de comunicación

El cliente Windows se comunicará con Atlas Assistant mediante la API remota de Atlas.

- Tailscale VPN proporciona el acceso de red privado previsto.
- HTTPS/TLS protege el transporte de la API.
- La vinculación y autenticación de Atlas son controles propios y no se sustituyen por la pertenencia a la red Tailscale.
- La API será la única puerta de entrada desde Desktop hacia las capacidades del servidor.

Desktop **no se conectará directamente a Ollama ni a Piper**. Tampoco tendrá conexiones directas a Docker, bases SQL o interfaces administrativas del host.

La recepción progresiva de respuestas forma parte de la experiencia prevista del Chat. El protocolo, framing, cancelación, reconexión y tratamiento de errores del transporte siguen pendientes de definición técnica.

## 4. Vinculación, credenciales y permisos

Cada instalación/dispositivo deberá vincularse explícitamente con Atlas.

Requisitos aprobados:

- La vinculación de dispositivo es independiente de Tailscale.
- Las credenciales son específicas de cada dispositivo.
- Las credenciales pueden revocarse individualmente.
- Las credenciales deben almacenarse de forma segura en Windows.
- El dispositivo tendrá permisos limitados a las funciones de conversación.

La vinculación no concede autoridad administrativa. El cliente Desktop no tendrá acceso directo a:

- Docker ni al runtime de contenedores.
- Archivos del servidor.
- Bases de datos SQL.
- Administración de identidades.
- Operaciones privilegiadas o de administración del host.

Los mecanismos concretos de emisión, renovación, expiración, almacenamiento local y revocación deben definirse en el diseño técnico. No se selecciona aquí un formato de token ni una tecnología específica de almacenamiento seguro.

## 5. Arquitectura de audio prevista

La dirección arquitectónica aprobada para una futura salida de voz es:

```text
Atlas Assistant
    |
    v
Generación de la respuesta
    |
    v
Atlas TTS Adapter
Interfaz independiente del motor de voz
    |
    v
Piper TTS
Generación de audio en Debian
    |
    v
Atlas API
    |
    v
Atlas Desktop
Entrega y reproducción del audio en Windows
```

Piper es el motor elegido provisionalmente. El adaptador TTS debe mantener desacoplado el Assistant del motor concreto para permitir cambios futuros sin acoplar el dominio conversacional a Piper.

Este diagrama describe la arquitectura objetivo, no el estado actual. La integración TTS, la instalación/configuración de Piper, la generación en Debian, la entrega por API y la reproducción en Windows no se consideran implementadas por esta decisión.

Phonon queda descartado y no debe tratarse como motor activo o alternativa seleccionada para la implementación actual.

## 6. Límites de seguridad

- Windows no se conectará directamente a Ollama ni a Piper.
- La API será la única puerta de entrada desde Desktop.
- Las credenciales o la conectividad de Tailscale no sustituyen la autenticación de Atlas.
- La identidad del dispositivo debe verificarse mediante el mecanismo de vinculación de Atlas.
- El dispositivo recibe únicamente permisos de conversación.
- No se concederá acceso directo a Docker, archivos, SQL, administración de identidades ni operaciones privilegiadas.
- La ausencia de conexión, identidad o autorización válida debe impedir el acceso; no se debe degradar a un modo de confianza implícita.

Estos límites son requisitos de diseño. Su aplicación efectiva deberá demostrarse mediante implementación y pruebas de seguridad.

## 7. Pendiente de definir

Los siguientes puntos permanecen abiertos:

1. Diseño visual detallado: colores, tipografía, iconografía, disposición y tema.
2. Voz e idioma concretos de Piper.
3. Formato y estrategia de entrega del audio.
4. Persistencia, retención y recuperación de conversaciones.
5. Diseño definitivo de la pantalla y el flujo de vinculación.
6. Protocolo de streaming, cancelación, reconexión y errores de la API.
7. Ciclo de vida de credenciales: emisión, renovación, expiración y revocación.
8. Tecnología concreta de almacenamiento seguro de credenciales en Windows.
9. Modelo de permisos y endpoints exactos expuestos a Desktop.

## 8. Estado de implementación

A la fecha de este registro, este documento **no afirma** que exista una aplicación WinUI 3, una API remota lista para Desktop, un flujo de vinculación funcional ni una integración de audio.

El README raíz describe el estado observado del Assistant y de Atlas en general. Las decisiones de este documento amplían la dirección aprobada para el cliente Windows, pero no alteran la descripción de lo que está implementado.

## 9. Regla de evolución

Cualquier cambio de framework de escritorio, plataforma inicial, frontera de comunicación, modelo de autenticación, permisos del dispositivo o motor TTS debe registrarse como una nueva decisión explícita. Las decisiones visuales y los detalles técnicos pendientes pueden resolverse durante el diseño sin presentarlos retroactivamente como decisiones ya tomadas.
