"""SQLite persistence adapter for native bindings to canonical AGENT identities."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import re
import sqlite3
from typing import Iterator
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
    NotFoundError,
)
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.native_agent_identity import (
    NativeAgentIdentityBinding,
    NativeAgentIdentityBindingStatus,
)
from atlas.core.native_identity import NativeIssuerStatus
from atlas.core.user_identity import validate_canonical_uuid4
from atlas.ports.native_agent_identity_authority import NativeAgentIdentityAuthorityPort


_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _utc_text(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field} debe ser datetime UTC")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ContractError(f"{field} debe ser datetime UTC")
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} persistido no es timestamp válido") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{field} persistido no está en UTC")
    return parsed


def _validate_digest(value: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ContractError("subject_digest debe ser SHA-256 lowercase")
    return value


class SQLiteNativeAgentIdentityAuthority(NativeAgentIdentityAuthorityPort):
    """Persists AGENT-only issuer bindings in a table separate from USER bindings."""

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
    def _from_row(row: sqlite3.Row) -> NativeAgentIdentityBinding:
        return NativeAgentIdentityBinding(
            binding_id=row["binding_id"],
            identity_id=row["identity_id"],
            issuer_id=row["issuer_id"],
            subject_digest=row["subject_digest"],
            status=NativeAgentIdentityBindingStatus(row["status"].lower()),
            revision=row["revision"],
            created_at=_parse_utc(row["created_at"], "created_at"),
            verified_at=_parse_utc(row["verified_at"], "verified_at"),
            revoked_at=(
                None if row["revoked_at"] is None
                else _parse_utc(row["revoked_at"], "revoked_at")
            ),
        )

    def get_native_agent_binding(
        self, issuer_id: str, subject_digest: str
    ) -> NativeAgentIdentityBinding | None:
        validate_canonical_uuid4(issuer_id, "issuer_id")
        _validate_digest(subject_digest)
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM native_agent_identity_bindings
                WHERE issuer_id = ? AND subject_digest = ?
                """,
                (issuer_id, subject_digest),
            ).fetchone()
            return None if row is None else self._from_row(row)

    def get_native_agent_binding_by_id(
        self, binding_id: str
    ) -> NativeAgentIdentityBinding | None:
        validate_canonical_uuid4(binding_id, "binding_id")
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_agent_identity_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            return None if row is None else self._from_row(row)

    def create_native_agent_binding(
        self,
        identity: CanonicalAgentIdentity,
        issuer_id: str,
        subject_digest: str,
        *,
        verified_at: datetime,
    ) -> NativeAgentIdentityBinding:
        if not isinstance(identity, CanonicalAgentIdentity):
            raise ContractError("identity debe ser CanonicalAgentIdentity")
        validate_canonical_uuid4(issuer_id, "issuer_id")
        _validate_digest(subject_digest)
        verified_at_text = _utc_text(verified_at, "verified_at")
        binding_id = str(uuid4())

        try:
            with self._write_connection() as connection:
                canonical = connection.execute(
                    """
                    SELECT identity_id, identity_kind, identity_status, revision, user_id
                    FROM identity_records
                    WHERE identity_id = ? AND identity_kind = 'agent' AND user_id IS NULL
                    """,
                    (identity.identity.identity_id,),
                ).fetchone()
                if canonical is None:
                    raise NotFoundError("identidad AGENT canónica no encontrada")
                if (
                    canonical["identity_status"] != identity.identity.status.value
                    or canonical["revision"] != identity.identity.revision
                ):
                    raise ConcurrencyError("la identidad AGENT suministrada está desactualizada")
                if canonical["identity_status"] != IdentityStatus.ACTIVE.value:
                    raise ContractError("el binding nativo requiere una identidad AGENT activa")
                if canonical["identity_kind"] != IdentityKind.AGENT.value or canonical["user_id"] is not None:
                    raise ContractError("el binding nativo requiere Identity(AGENT) sin UserId")

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
                    INSERT INTO native_agent_identity_bindings (
                        binding_id, identity_id, issuer_id, subject_digest,
                        status, revision, created_at, verified_at, revoked_at
                    ) VALUES (?, ?, ?, ?, 'ACTIVE', 1, ?, ?, NULL)
                    """,
                    (
                        binding_id, identity.identity.identity_id, issuer_id,
                        subject_digest, verified_at_text, verified_at_text,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM native_agent_identity_bindings WHERE binding_id = ?",
                    (binding_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError("binding nativo AGENT no pudo releerse")
                return self._from_row(row)
        except sqlite3.IntegrityError as exc:
            raise IdentityConflictError(
                "binding nativo AGENT duplicado o conflicto de integridad"
            ) from exc

    def revoke_native_agent_binding(
        self,
        binding_id: str,
        *,
        expected_revision: int,
        revoked_at: datetime,
    ) -> NativeAgentIdentityBinding:
        validate_canonical_uuid4(binding_id, "binding_id")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser entero positivo")
        revoked_at_text = _utc_text(revoked_at, "revoked_at")
        with self._write_connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_agent_identity_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("binding nativo AGENT no encontrado")
            current = self._from_row(row)
            if current.revision != expected_revision:
                raise ConcurrencyError("revisión de binding nativo AGENT obsoleta")
            if current.status is NativeAgentIdentityBindingStatus.REVOKED:
                return current
            if revoked_at < current.created_at:
                raise ContractError("revoked_at no puede preceder created_at")
            cursor = connection.execute(
                """
                UPDATE native_agent_identity_bindings
                SET status = 'REVOKED', revision = revision + 1, revoked_at = ?
                WHERE binding_id = ? AND revision = ? AND status = 'ACTIVE'
                """,
                (revoked_at_text, binding_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError(
                    "el binding nativo AGENT cambió durante la revocación"
                )
            updated = connection.execute(
                "SELECT * FROM native_agent_identity_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if updated is None:
                raise sqlite3.DatabaseError(
                    "el binding nativo AGENT desapareció durante la revocación"
                )
            return self._from_row(updated)
