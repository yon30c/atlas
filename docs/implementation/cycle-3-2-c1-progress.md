# Cycle 3.2-C1 — progreso de implementación

**Rama:** `feature/cycle-3-2-c1-native-credentials`  
**Base:** PR #8, `design/cycle-3-2-c1-native-authentication-contracts`  
**Estado:** primer slice de credenciales implementado; pendiente de validación en Debian.

## Slice C1-1 — credenciales y Argon2id

Se añadieron:

- `LoginHandle`: canonicalización ASCII lowercase, longitud 3–64 y patrón estricto.
- Política de contraseña nueva: mínimo 12 puntos de código Unicode, máximo 1024 bytes UTF-8, sin NUL, sin trim ni normalización silenciosa.
- `Argon2idParameters`: todos los parámetros son obligatorios y validados; no existen defaults de producción implícitos.
- Puerto `PasswordHasherPort`.
- Adaptador `Argon2idPasswordHasher` sobre `argon2-cffi`, usando explícitamente `Type.ID`, salt aleatorio administrado por la biblioteca, PHC encoded hashes, verificación y detección de rehash.
- Pruebas unitarias focalizadas para normalización, límites, UTF-8, Argon2id, salts diferentes, verificación, hashes inválidos y detección de rehash.
- Dependencia runtime `argon2-cffi>=23.1.0`.

Este slice no contiene ni habilita login, lookup de cuentas, almacenamiento de credenciales, proofs, sesiones, bootstrap, migraciones, endpoints o integración de consola. El adaptador requiere parámetros explícitos inyectados por composición confiable. Los parámetros pequeños usados en tests son exclusivamente de test y no representan valores de producción.

## Hallazgos y bloqueos que se conservan

1. El contrato legacy `AuthenticatedUserSubject` / `IdentitySubjectBindingPort` existe, pero no acredita autenticación nativa y no se reutiliza.
2. Identity(USER) y UserId ya existen; la siguiente migración esperada sigue siendo v19, sujeta a confirmar el baseline integrado.
3. `SQLiteLocalAuthorityUnitOfWork` comparte la transacción física, pero todavía debe ampliarse con repositorios Identity issuer/binding y Authentication Authority. El store de authority changes no equivale a un coordinador de Consistency.
4. **Grant inicial del bootstrap sin perfil CAM aprobado:** el modelo Grant exige owner_user_id, subject_identity_id, project_id, environment, resource_type, IDs concretos de recurso, acciones explícitas y expiración. El diseño C1 permite crear el usuario sin activarlo si no hay perfil administrativo mínimo aprobado, pero la matriz de pruebas C1 exige que Grant y los demás agregados existan todos o ninguno. Antes de implementar bootstrap hay que resolver esa tensión con un perfil CAM explícito y acotado o aprobar formalmente un bootstrap que no conceda Grant ni active operaciones protegidas. No se inventará un Grant global ni un proyecto/entorno ficticio.
5. Los parámetros Argon2id de producción requieren benchmark en el hardware objetivo. No se fijan con valores de CI o de test.

## Validación

La suite de este slice todavía no se ha ejecutado en el checkout Debian del propietario. No se declara validación exitosa. Tras instalar la nueva dependencia, ejecutar primero las pruebas focalizadas y después la suite completa y compileall. La aceptación de producción requiere además benchmark Argon2id en el hardware objetivo.

## Próximo slice

Una vez confirmada la validación de C1-1, continuar con modelos/puertos de NativeAuthenticator, NativeSubject y proof, manteniendo fuera de alcance sesiones y exposición de login. La persistencia y migración se implementarán solo después de cerrar el diseño de issuer/binding y la decisión CAM del bootstrap.
