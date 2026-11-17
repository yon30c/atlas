# Cycle 3.2-C1 — progreso de implementación

**Rama:** `feature/cycle-3-2-c1-native-credentials`  
**Base:** PR #8, `design/cycle-3-2-c1-native-authentication-contracts`  
**Estado:** C1-1 y C1-2 validados en Debian; C1-3 implementado como contratos de Identity Authority y pendiente de validación.

## Slice C1-1 — credenciales y Argon2id

Se añadieron:

- `LoginHandle`: canonicalización ASCII lowercase, longitud 3–64 y patrón estricto.
- Política de contraseña nueva: mínimo 12 puntos de código Unicode, máximo 1024 bytes UTF-8, sin NUL, sin trim ni normalización silenciosa.
- `Argon2idParameters`: todos los parámetros son obligatorios y validados; no existen defaults de producción implícitos.
- Puerto `PasswordHasherPort`.
- Adaptador `Argon2idPasswordHasher` sobre `argon2-cffi`, usando explícitamente `Type.ID`, salt aleatorio administrado por la biblioteca, PHC encoded hashes, verificación y detección de rehash.
- Dependencia runtime `argon2-cffi>=23.1.0`.

**Validación Debian confirmada por el propietario:**

- Suite completa C1-1: 1,232 pruebas, OK.
- Pruebas focalizadas C1-1: 14 pruebas, OK.
- `python -m compileall -q src tests`: exit code 0.
- Git alineado con origin y árbol limpio antes de C1-2.

Los parámetros pequeños usados en tests son exclusivamente de test y no representan valores de producción. La aceptación de producción requiere benchmark Argon2id en el hardware objetivo.

## Slice C1-2 — contratos de autenticación nativa

Se añadieron en `src/atlas/authentication/native.py`:

- `NativeSubject`: token base64url canónico generado con 32 bytes CSPRNG; expone digest SHA-256 y redacta el valor en repr.
- `NativeProofReference`: referencia one-shot de 256 bits con digest SHA-256 y repr redactado.
- `NativeAuthenticator`: agregado de Authentication Authority con IDs UUIDv4, LoginHandle, PHC Argon2id, revisión de credencial y estados ACTIVE/SUSPENDED/REVOKED. No contiene UserId, Identity ni Grant.
- `NativeAuthenticationProof`: metadata persistible digest-only, con issuer, subject, authenticator, revisión, timestamps UTC, audience y estado. La referencia raw no forma parte del registro.
- Pruebas unitarias para generación/forma de tokens, redacción, digest, invariantes de IDs, PHC, revisión, fechas, audience y estados.

Validación Debian confirmada:
- Suite completa: 1,239 pruebas, OK.
- El checkout reportado está alineado con origin y limpio en `c69ebe4`.
- `compileall` focalizado no fue reportado explícitamente para este slice.

Este slice no implementa repositorios, emisión/consumo atómico de proof, bootstrap, migraciones, sesiones, endpoints ni composición productiva.

## Slice C1-3 — Identity Authority: issuer y binding nativo

Se añadieron:

- `src/atlas/core/native_identity.py`:
  - `NativeIdentityIssuer`, con realm lógico estable, perfil explícito `NATIVE_AUTHORITY_PROOF`, estado y revisión.
  - `NativeIdentityBinding`, que vincula issuer + digest del subject con un `identity_id` canónico, timestamps UTC, revisión y tombstone terminal de revocación.
- `src/atlas/ports/native_identity_authority.py`:
  - puerto de Identity Authority para consultar/crear issuer, consultar/crear binding y revocar con CAS.
  - La creación de binding recibe `CanonicalUserIdentity`, no un ID elegido libremente por el caller.
  - El puerto no autentica credenciales, no emite proofs y no concede Grants.
- Pruebas unitarias para IDs, realm, perfil, digest, timestamps, revisión y estados.

**Validación C1-3:** pendiente en Debian. Ejecutar:

```bash
python -m unittest discover -s tests/unit -p 'test_native_identity_authority_contracts.py' -v
python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
python -m unittest discover -s tests -t tests -v
git status --short --branch
git log -1 --oneline
```

C1-3 todavía no implementa adaptador SQLite ni altera `SQLiteIdentityAuthority` o `SQLiteLocalAuthorityUnitOfWork`.

## Hallazgos y bloqueos que se conservan

1. El contrato legacy `AuthenticatedUserSubject` / `IdentitySubjectBindingPort` existe, pero no acredita autenticación nativa y no se reutiliza.
2. Identity(USER) y UserId ya existen; la siguiente migración esperada sigue siendo v19, sujeta a confirmar el baseline integrado.
3. `SQLiteLocalAuthorityUnitOfWork` comparte la transacción física, pero todavía debe ampliarse con repositorios Identity issuer/binding y Authentication Authority. El store de authority changes no equivale a un coordinador de Consistency.
4. **Grant inicial del bootstrap sin perfil CAM aprobado:** el modelo Grant exige owner_user_id, subject_identity_id, project_id, environment, resource_type, IDs concretos de recurso, acciones explícitas y expiración. Antes de implementar bootstrap hay que resolver la tensión entre bootstrap sin Grant y las pruebas todo-o-nada, mediante un perfil CAM explícito y acotado o aprobación formal de un bootstrap sin activación. No se inventará un Grant global ni un proyecto/entorno ficticio.
5. Los parámetros Argon2id de producción requieren benchmark en el hardware objetivo.

## Próximo slice

Tras validar C1-3, implementar el adaptador de Identity Authority para issuer/binding con pruebas de unicidad/tombstone/CAS. Después definir repositorios de Authentication Authority y el consumo one-shot de proof bajo la misma UoW física. La migración v19 y bootstrap permanecen bloqueados hasta confirmar baseline y cerrar la decisión CAM.
