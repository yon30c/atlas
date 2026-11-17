# Cycle 3.2-C1 — progreso de implementación

**Rama:** `feature/cycle-3-2-c1-native-credentials`  
**Base:** PR #8, `design/cycle-3-2-c1-native-authentication-contracts`  
**Estado:** C1-1 validado en Debian; C1-2 implementado como contratos de dominio y pendiente de validación.

## Slice C1-1 — credenciales y Argon2id

Se añadieron:

- `LoginHandle`: canonicalización ASCII lowercase, longitud 3–64 y patrón estricto.
- Política de contraseña nueva: mínimo 12 puntos de código Unicode, máximo 1024 bytes UTF-8, sin NUL, sin trim ni normalización silenciosa.
- `Argon2idParameters`: todos los parámetros son obligatorios y validados; no existen defaults de producción implícitos.
- Puerto `PasswordHasherPort`.
- Adaptador `Argon2idPasswordHasher` sobre `argon2-cffi`, usando explícitamente `Type.ID`, salt aleatorio administrado por la biblioteca, PHC encoded hashes, verificación y detección de rehash.
- Dependencia runtime `argon2-cffi>=23.1.0`.

**Validación Debian confirmada por el propietario:**

- Suite completa: 1,232 pruebas, OK.
- Pruebas focalizadas C1-1: 14 pruebas, OK.
- `python -m compileall -q src tests`: exit code 0.
- Git: rama alineada con origin y árbol limpio antes de iniciar C1-2.

Los parámetros pequeños usados en tests son exclusivamente de test y no representan valores de producción. La aceptación de producción requiere benchmark Argon2id en el hardware objetivo.

## Slice C1-2 — NativeSubject, NativeAuthenticator y proof metadata

Se añadieron en `src/atlas/authentication/native.py`:

- `NativeSubject`: token base64url canónico generado con 32 bytes CSPRNG; expone digest SHA-256 y redacta el valor en repr.
- `NativeProofReference`: referencia one-shot de 256 bits con digest SHA-256 y repr redactado.
- `NativeAuthenticator`: agregado de Authentication Authority con IDs UUIDv4, LoginHandle, PHC Argon2id, credential revision y estado ACTIVE/SUSPENDED/REVOKED. No contiene UserId, Identity ni Grant.
- `NativeAuthenticationProof`: metadata persistible digest-only, con issuer, subject, authenticator, revisión, timestamps UTC, audience y estado. La referencia raw no forma parte del registro.
- Pruebas unitarias para generación/forma de tokens, redacción, digest, invariantes de IDs, PHC, revisión, fechas, audience y estados.

Este slice contiene únicamente modelos/contratos de dominio. No implementa repositorios, puertos de persistencia, issuer/binding, emisión/consumo atómico de proof, bootstrap, migraciones, sesiones, endpoints ni composición productiva. No se debe interpretar como autenticación operativa.

**Validación C1-2:** pendiente de ejecución en Debian. Ejecutar primero:

```bash
python -m unittest discover -s tests/unit -p 'test_native_authentication_native_contracts.py' -v
python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
```

Después, suite completa.

## Hallazgos y bloqueos que se conservan

1. El contrato legacy `AuthenticatedUserSubject` / `IdentitySubjectBindingPort` existe, pero no acredita autenticación nativa y no se reutiliza.
2. Identity(USER) y UserId ya existen; la siguiente migración esperada sigue siendo v19, sujeta a confirmar el baseline integrado.
3. `SQLiteLocalAuthorityUnitOfWork` comparte la transacción física, pero todavía debe ampliarse con repositorios Identity issuer/binding y Authentication Authority. El store de authority changes no equivale a un coordinador de Consistency.
4. **Grant inicial del bootstrap sin perfil CAM aprobado:** el modelo Grant exige owner_user_id, subject_identity_id, project_id, environment, resource_type, IDs concretos de recurso, acciones explícitas y expiración. El diseño C1 permite crear el usuario sin activarlo si no hay perfil administrativo mínimo aprobado, pero la matriz de pruebas C1 exige que Grant y los demás agregados existan todos o ninguno. Antes de implementar bootstrap hay que resolver esa tensión con un perfil CAM explícito y acotado o aprobar formalmente un bootstrap que no conceda Grant ni active operaciones protegidas. No se inventará un Grant global ni un proyecto/entorno ficticio.
5. Los parámetros Argon2id de producción requieren benchmark en el hardware objetivo. No se fijan con valores de CI o de test.

## Próximo slice

Tras validar C1-2, inspeccionar y definir los puertos/repositorios necesarios para Authentication Authority y el límite de Identity Authority. La persistencia, issuer/binding y migración se implementarán solo después de cerrar sus contratos y confirmar el baseline integrado. El bootstrap continúa bloqueado por la decisión CAM indicada arriba.
