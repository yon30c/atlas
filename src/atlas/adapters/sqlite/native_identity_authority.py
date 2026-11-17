"""SQLite persistence adapter for native Identity Authority issuer/bindings."""

from contextlib import contextmanager
from datetime import datetime, timezone
import re
import sqlite3
from typing import Iterator
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
    NotFoundError,
)
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.native_identity import (
    NativeIdentityBinding,
    NativeIdentityBindingStatus,
    NativeIdentityIssuer,
    NativeIssuerProfile,
    NativeIssuerStatus,
)
from atlas.core.user_identity import (
    CanonicalUserIdentity,
    validate_canonical_uuid4,
)


_REALM_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}", re.ASCII)
_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError("timestamp debe ser datetime con zona horaria")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ContractError("timestamp debe estar en UTC")
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} persistido no es timestamp válido") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractError(f"{field} persistido no está en UTC")
    return parsed


def _validate_realm(value: str) -> str:
    if not isinstance(value, str) or _REALM_RE.fullmatch(value) is None:
        raise ContractError("realm debe ser lowercase ASCII de 2 a 64 caracteres")
    return value


def _validate_digest(value: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ContractError("subject_digest debe ser SHA-256 lowercase")
    return value


class SQLiteNativeIdentityAuthority:
    """Persists native issuers and immutable subject-to-Identity(USER) bindings."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        unit_of_work: SQLiteUnitOfWork | None = None,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if unit_of_work is not None and not isinstance(unit_of_work, SQLiteUnitOfWork):
            raise ContractError("unit_of_work debe ser SQLiteUnitOfWork")
        self._database = database
        self._unit_of_work = unit_of_work

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.connection() as connection:
                yield connection

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.unit_of_work() as unit:
                yield unit._connection_for(self._database)

    @staticmethod
    def _issuer_from_row(row: sqlite3.Row) -> NativeIdentityIssuer:
        return NativeIdentityIssuer(
            issuer_id=row["issuer_id"],
            realm=row["realm"],
            profile=NativeIssuerProfile(row["profile"]),
            status=NativeIssuerStatus(row["status"]),
            revision=row["revision"],
        )

    @staticmethod
    def _binding_from_row(row: sqlite3.Row) -> NativeIdentityBinding:
        return NativeIdentityBinding(
            binding_id=row["binding_id"],
            identity_id=row["identity_id"],
            issuer_id=row["issuer_id"],
            subject_digest=row["subject_digest"],
            status=NativeIdentityBindingStatus(row["status"]),
            revision=row["revision"],
            created_at=_parse_utc(row["created_at"], "created_at"),
            verified_at=_parse_utc(row["verified_at"], "verified_at"),
            revoked_at=(
                None if row["revoked_at"] is None
                else _parse_utc(row["revoked_at"], "revoked_at")
            ),
        )

    def get_native_issuer(self, realm: str) -> NativeIdentityIssuer | None:
        _validate_realm(realm)
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_identity_issuers WHERE realm = ?",
                (realm,),
            ).fetchone()
            return None if row is None else self._issuer_from_row(row)

    def create_native_issuer(self, realm: str) -> NativeIdentityIssuer:
        _validate_realm(realm)
        issuer = NativeIdentityIssuer(
            issuer_id=str(uuid4()),
            realm=realm,
            profile=NativeIssuerProfile.NATIVE_AUTHORITY_PROOF,
            status=NativeIssuerStatus.ACTIVE,
        )
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO native_identity_issuers (
                        issuer_id, realm, profile, status, revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (issuer.issuer_id, issuer.realm, issuer.profile.value,
                     issuer.status.value, now, now),
                )
                row = connection.execute(
                    "SELECT * FROM native_identity_issuers WHERE issuer_id = ?",
                    (issuer.issuer_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError("issuer nativo no pudo releerse")
                return self._issuer_from_row(row)
        except sqlite3.IntegrityError as exc:
            raise IdentityConflictError("realm o issuer nativo ya registrado") from exc

    def get_native_binding(
        self,
        issuer_id: str,
        subject_digest: str,
    ) -> NativeIdentityBinding | None:
        validate_canonical_uuid4(issuer_id, "issuer_id")
        _validate_digest(subject_digest)
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM native_identity_bindings
                WHERE issuer_id = ? AND subject_digest = ?
                """,
                (issuer_id, subject_digest),
            ).fetchone()
            return None if row is None else self._binding_from_row(row)

    def create_native_binding(
        self,
        identity: CanonicalUserIdentity,
        issuer_id: str,
        subject_digest: str,
        *,
        verified_at: datetime,
    ) -> NativeIdentityBinding:
        if not isinstance(identity, CanonicalUserIdentity):
            raise ContractError("identity debe ser CanonicalUserIdentity")
        validate_canonical_uuid4(issuer_id, "issuer_id")
        _validate_digest(subject_digest)
        verified_at_text = _utc_text(verified_at)
        binding_id = str(uuid4())

        try:
            with self._write_connection() as connection:
                canonical = SQLiteIdentityAuthority._select_user(connection, identity.user_id)
                if canonical is None:
                    raise NotFoundError("usuario canónico no encontrado")
                if canonical["identity_id"] != identity.identity.identity_id:
                    raise IdentityConflictError("la identidad canónica suministrada no coincide con UserId")
                if (
                    canonical["identity_status"] != identity.identity.status.value
                    or canonical["revision"] != identity.identity.revision
                ):
                    raise ConcurrencyError("la identidad canónica suministrada está desactualizada")
                if canonical["identity_kind"] != IdentityKind.USER.value:
                    raise ContractError("el binding nativo requiere Identity(USER)")
                if canonical["identity_status"] != IdentityStatus.ACTIVE.value:
                    raise ContractError("el binding nativo requiere una identidad USER activa")

                issuer = connection.execute(
                    "SELECT status FROM native_identity_issuers WHERE issuer_id = ?",
                    (issuer_id,),
                ).fetchone()
                if issuer is None:
                    raise NotFoundError("issuer nativo no encontrado")
                if issuer["status"] != NativeIssuerStatus.ACTIVE.value:
                    raise ContractError("no se puede vincular un issuer nativo revocado")

                connection.execute(
                    """
                    INSERT INTO native_identity_bindings (
                        binding_id, identity_id, issuer_id, subject_digest,
                        status, revision, created_at, verified_at, revoked_at
                    ) VALUES (?, ?, ?, ?, 'ACTIVE', 1, ?, ?, NULL)
                    """,
                    (binding_id, identity.identity.identity_id, issuer_id,
                     subject_digest, verified_at_text, verified_at_text),
                )
                row = connection.execute(
                    "SELECT * FROM native_identity_bindings WHERE binding_id = ?",
                    (binding_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError("binding nativo no pudo releerse")
                return self._binding_from_row(row)
        except sqlite3.IntegrityError as exc:
            raise IdentityConflictError(
                "binding nativo duplicado o conflicto de integridad"
            ) from exc

    def revoke_native_binding(
        self,
        binding_id: str,
        *,
        expected_revision: int,
        revoked_at: datetime,
    ) -> NativeIdentityBinding:
        validate_canonical_uuid4(binding_id, "binding_id")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser entero positivo")
        revoked_at_text = _utc_text(revoked_at)
        with self._write_connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_identity_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("binding nativo no encontrado")
            current = self._binding_from_row(row)
            if current.revision != expected_revision:
                raise ConcurrencyError("revisión de binding nativo obsoleta")
            if current.status is NativeIdentityBindingStatus.REVOKED:
                return current
            if revoked_at < current.created_at:
                raise ContractError("revoked_at no puede preceder created_at")
            cursor = connection.execute(
                """
                UPDATE native_identity_bindings
                SET status = 'REVOKED', revision = revision + 1, revoked_at = ?
                WHERE binding_id = ? AND revision = ? AND status = 'ACTIVE'
                """,
                (revoked_at_text, binding_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError("el binding nativo cambió durante la revocación")
            updated = connection.execute(
                "SELECT * FROM native_identity_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if updated is None:
                raise sqlite3.DatabaseError("binding nativo desapareció durante la revocación")
            return self._binding_from_row(updated)
