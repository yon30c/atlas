# Atlas

Atlas es un entorno personal de asistencia, coordinación y automatización de proyectos. Su propósito es permitir que el propietario consulte y gestione sus proyectos y delegue trabajo a agentes y herramientas bajo límites explícitos, verificables y revocables.

La arquitectura se guía por seguridad por defecto, mínimo privilegio, aislamiento, mediación, trazabilidad, recuperación segura y portabilidad. La autonomía nunca equivale a autoridad ilimitada.

## Estado del repositorio

El repositorio contiene una primera experiencia conversacional local funcional y una implementación progresiva de contratos de dominio, autorización y Memory Engine. No todos esos módulos están integrados en un único flujo operativo.

**Importante:** la presencia de un módulo, contrato, migración o prueba no demuestra por sí sola que una capacidad esté completa o habilitada en runtime.

### Capacidades implementadas en la línea de trabajo

- **Atlas Assistant / AtlasCore:** experiencia conversacional de consola, modelos neutrales de solicitud/respuesta, contexto de sesión y streaming.
- **Proveedor LLM local:** adaptador Ollama sobre `/api/chat`, restringido a endpoints loopback (`localhost`, `127.0.0.1`, `::1`). No se admiten proveedores remotos ni proxies del entorno en esta composición.
- **Historial conversacional:** `InMemoryConversationHistory`, separado por `conversation_id`, con límite de hasta 8 turnos y 2000 caracteres por mensaje histórico. Es temporal y desaparece al terminar el proceso.
- **SQLite / consistencia local:** infraestructura de base SQLite, UoW, journal, migraciones y mecanismos parciales de recuperación.
- **D4O-I C.4.1:** `SQLiteAuthorityChangeStore` con reserva durable e idempotencia semántica de operaciones. Su alcance es almacenamiento de operaciones; no es un coordinador completo de revocación ni de cambios de autoridad.

La ejecución local del propietario reportó 787 pruebas de la suite completa finalizadas con `OK` para el estado C.4.1 y sus correcciones de tests. Esta evidencia corresponde a esa ejecución local; no implica que GitHub Actions/CI haya pasado ni que las capacidades pendientes estén verificadas.

### Capacidades en diseño o implementación parcial

- Memory Engine y Memory Gateway: contratos de dominio, scopes PRIVATE/PROJECT, versiones, procedencia, autorización y consistencia.
- Identity, bindings y contexto de identidad verificada.
- CAM, Grants y coordinación de cambios de autoridad.
- Admisión durable de lecturas y recuperación protegida.
- Persistencia canónica compartida de Memory, Identity, Project, Environment y CAM.

Aún no debe afirmarse que existe una persistencia completa de contenido Memory, un coordinador SQLite completo de revocación, una implementación de `admit_read`, egress protegido completo o runtime protegido habilitado.

### Visión de arquitectura

La descomposición objetivo es:

1. **Atlas Assistant / AtlasCore:** interfaz y coordinación de solicitudes.
2. **Memory Engine / Memory Gateway:** memoria persistente gobernada por scope, procedencia, versiones y autorización.
3. **Identity Authority:** identidad canónica y bindings autenticados.
4. **CAM:** autorización central por operación y recurso exactos.
5. **Consistency:** invalidación, fencing, admisiones, journal y recuperación.
6. **Project / Environment:** identidad, configuración, estado deseado y estado observado de proyectos y entornos.
7. **Broker:** frontera pequeña y explícita para operaciones de runtime Docker Rootless.
8. **Skills y agentes:** capacidades extensibles sujetas a procedencia, revisión de código/dependencias, declaración y aprobación de permisos, instalación controlada, aislamiento, auditoría y desactivación.
9. **Backup / Manifest / Restore / Verification:** reconstrucción portable y verificación antes de reactivar cargas de trabajo.

Esta arquitectura es una visión por etapas. La existencia de contratos no implica que todos los componentes estén implementados o integrados. Atlas Broker se mantiene como componente/proyecto separado y no se debe asumir una integración operativa con AtlasCore.

## Principios de seguridad

- Denegar por defecto y fallar cerrado ante identidad, contexto, autorización o evidencia incompletos.
- Separar autenticación, identidad y autorización.
- Verificar permisos en cada operación protegida.
- Limitar Grants a consumidor/proyecto, entorno, recurso, operación, límites y vigencia explícitos.
- No conceder permisos por conocer IDs.
- Aislar consumidores y proyectos; no hay acceso ni búsqueda cross-consumer/project por defecto.
- Mantener aprobación, rechazo y Forget de memoria como acciones directas y no delegables del propietario.
- Coordinar cambios de autoridad con invalidación y fencing previos.
- No restaurar proyectos o Skills automáticamente después de migración/recuperación.
- No almacenar secretos en documentación ni respaldos sin cifrado y custodia apropiada.

## Contratos y documentación normativa

El documento normativo principal es:

- [Contrato de diseño Atlas v1 — revisión 4](Contrato-de-diseno-Atlas-v1.md)

Enmiendas y contratos relacionados:

- [B1-A-06 — identidad, Project/Environment y persistencia compartida](docs/contracts/b1-a06-identity-project-environment-and-persistence.md)
- [B1-B-02 — modelo lógico integrado y matriz de consistencia contractual](docs/design/b1-b02-logical-model-and-contract-consistency.md)
- [B1-B-03A-01 — propuesta de aclaración owner_id / Identity Binding](docs/contracts/b1-b03a-01-owner-identity-binding-clarification.md)
- [Contrato técnico de Memory Engine](docs/design/memory-engine-technical-contract.md)
- [Independencia de Memory Engine respecto a consumidores](docs/design/memory-engine-project-independence-implementation.md)
- [DM-01 — especificación del modelo de dominio](docs/design/domain-model-specification-dm-01.md)
- [ME-D4O-B — admisión durable de lectura](docs/design/ME-D4O-B-durable-read-admission.md)
- [ME-D4O-I C.2 — verificación y consumo de pruebas de revocación](docs/design/me-d4o-i-c2-proof-verification-and-one-shot-consumption.md)
- [ME-D4O-I C.3 — coordinación de revocación de Grants](docs/design/me-d4o-i-c3-grant-revocation-coordination.md)
- [ME-D4O-I C.4.1 — almacenamiento durable SQLite de cambios de autoridad](docs/design/me-d4o-i-c4-sqlite-durable-authority-store.md)
- [README de Memory Engine](docs/memory-engine/README.md)

La enmienda B1-A-06 adopta B1-A-01 a B1-A-05 como decisiones posteriores al baseline anterior. B1-B-02 consolida el modelo lógico y registra las discrepancias que deben resolverse antes del diseño físico. No constituye autorización de implementación.

## Ejecución local

Desde la raíz del repositorio:

```bash
PYTHONPATH=src python -m atlas
```

Para instalar el comando en el entorno activo:

```bash
python -m pip install -e .
atlas
```

Modo informativo sin proveedor LLM:

```bash
ATLAS_MODE=offline PYTHONPATH=src python -m atlas
```

Configuración de consola:

- `ATLAS_MODEL`: tag del modelo local (predeterminado: `gemma4:e2b`).
- `ATLAS_OLLAMA_URL`: endpoint Ollama; debe ser loopback.
- `ATLAS_MODE=offline`: modo informativo sin LLM.

Atlas no instala, descarga ni inicia Ollama automáticamente.

## Pruebas

La suite se ejecuta desde el entorno del proyecto:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

La lista y el resultado de las pruebas deben corresponder al checkout concreto y quedar registrados con su commit. No se debe inferir un resultado CI a partir de una ejecución local.

## Hoja de ruta inmediata

**B1-B-03A está CERRADO NORMATIVAMENTE** (15-11-2026). Sus enmiendas se incorporaron y verificaron en DM-01, B1-A-06, identity.md y operation-context.md. No implica implementación.

Diseños técnicos elaborados en la rama `docs/b1-b03-identity-authority-roadmap`:

1. **B1-B-03B — Diseño físico de Identity Authority / SQLite:** [documento](docs/design/b1-b03b-identity-authority-physical-design.md). Modelo relacional candidato, constraints, ownership, UoW, CAS, evolución v4→v5 y compatibilidad.
2. **B1-B-03C — Ciclo de vida y seguridad de cuentas:** [documento](docs/design/b1-b03c-identity-lifecycle-and-account-security.md). Linking, unlink, cambio de proveedor, issuers, recovery y merge.
3. **B1-B-03D — VerifiedIdentityContext y evidencia:** [documento](docs/design/b1-b03d-verified-identity-and-evidence.md). Validación criptográfica, nonce/replay, actor/delegación, auditoría y expiración.
4. **B1-B-03E — Migración legacy y rollout:** [documento](docs/design/b1-b03e-legacy-migration-and-rollout.md). Inventario, mapping manifest, dry-run, backup/restore, cutover y reconciliación.

### Estado real y bloqueos

- El inventario confirmó SQLite schema v4, migraciones con checksums inmutables, Identity sin persistencia canónica completa y ausencia de PRIVATE_MEMORY_AUTHORIZATION en AuthorityKind/schema v4.
- El diseño propone una migración v5 aditiva; no se modificaron migraciones ni bases de datos.
- No se implementaron repositorios Identity/CAM, issuer adapters ni autenticación externa.
- No se habilitaron linking, unlink, recovery, merge, VerifiedIdentityContext, Memory Gateway protegido ni Recovery Gate.
- Permanecen pendientes decisiones de proveedor de secretos, representación protegida del subject, protocolo/issuer, fuente canónica de consumer_id, política de recuperación y mapping legacy.
- La migración real requiere pruebas v1→v5 y v4→v5, preservación de filas/FKs/checksums, backup restaurable y autorización específica de ejecución.

**Siguiente trabajo técnico:** cerrar los bloqueos de implementación y preparar la migración v5 en una rama de código aislada; ejecutar la suite completa y pruebas de upgrade/downgrade/recovery en DB temporal. No aplicar cambios a datos reales ni a componentes protegidos sin autorización de ejecución correspondiente.

## Límites de seguridad y alcance

- No modificar Atlas Broker, Registry, servicios protegidos ni producción como parte del trabajo de Memory Engine.
- No abrir el Recovery Gate ni habilitar lecturas/egress protegidos antes del bootstrap, recuperación y validaciones exigidas.
- No realizar merge, PR, deploy ni cambios de políticas sin autorización explícita.
- Antes de migraciones o cambios de estado: respaldo verificado, integridad y permisos comprobados.
