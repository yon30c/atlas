"""SQLite persistence for native Authentication Authority credentials and proofs."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticationProofStatus,
    NativeAuthenticator,
    NativeAuthenticatorStatus,
    NativeProofReference,
    NativeSubject,
)
from atlas.core.errors import ConcurrencyError, ContractError, IdentityConflictError
from atlas.ports.native_authentication_authority import NativeAuthenticationAuthorityPort


def _utc_text(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field} debe ser datetime con zona horaria")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} persistido no es timestamp válido") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{field} persistido no está en UTC")
    return parsed


class SQLiteNativeAuthenticationAuthority(NativeAuthenticationAuthorityPort):
    """Stores PHC verifiers and digest-only, audience-bound, one-shot proofs."""

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
    def _authenticator_from_row(row: sqlite3.Row) -> NativeAuthenticator:
        return NativeAuthenticator(
            authenticator_id=row["authenticator_id"],
            issuer_id=row["issuer_id"],
            native_subject=NativeSubject(row["native_subject"]),
            login_handle=LoginHandle(row["login_handle"]),
            password_hash_phc=row["password_hash_phc"],
            credential_revision=row["credential_revision"],
            status=NativeAuthenticatorStatus(row["status"]),
        )

    @staticmethod
    def _proof_from_row(row: sqlite3.Row) -> NativeAuthenticationProof:
        return NativeAuthenticationProof(
            proof_id=row["proof_id"],
            reference_digest=row["reference_digest"],
            issuer_id=row["issuer_id"],
            native_subject=NativeSubject(row["native_subject"]),
            authenticator_id=row["authenticator_id"],
            credential_revision=row["credential_revision"],
            authenticated_at=_parse_utc(row["authenticated_at"], "authenticated_at"),
            expires_at=_parse_utc(row["expires_at"], "expires_at"),
            audience=row["audience"],
            status=NativeAuthenticationProofStatus(row["status"]),
        )

    def create_native_authenticator(
        self, authenticator: NativeAuthenticator
    ) -> NativeAuthenticator:
        if not isinstance(authenticator, NativeAuthenticator):
            raise ContractError("authenticator debe ser NativeAuthenticator")
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO native_authenticators (
                        authenticator_id, issuer_id, native_subject, login_handle,
                        password_hash_phc, credential_revision, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        authenticator.authenticator_id,
                        authenticator.issuer_id,
                        authenticator.native_subject.value,
                        authenticator.login_handle.value,
                        authenticator.password_hash_phc,
                        authenticator.credential_revision,
                        authenticator.status.value,
                        _utc_text(datetime.now(timezone.utc), "created_at"),
                        _utc_text(datetime.now(timezone.utc), "updated_at"),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM native_authenticators WHERE authenticator_id = ?",
                    (authenticator.authenticator_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError("autenticador nativo no pudo releerse")
                return self._authenticator_from_row(row)
        except sqlite3.IntegrityError as exc:
            raise IdentityConflictError(
                "autenticador duplicado o conflicto de issuer/login handle/subject"
            ) from exc

    def get_native_authenticator(
        self, authenticator_id: str
    ) -> NativeAuthenticator | None:
        if not isinstance(authenticator_id, str) or not authenticator_id:
            raise ContractError("authenticator_id debe ser no vacío")
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_authenticators WHERE authenticator_id = ?",
                (authenticator_id,),
            ).fetchone()
            return None if row is None else self._authenticator_from_row(row)

    def get_native_authenticator_by_login_handle(
        self, issuer_id: str, login_handle: str
    ) -> NativeAuthenticator | None:
        if not isinstance(issuer_id, str) or not issuer_id:
            raise ContractError("issuer_id debe ser no vacío")
        handle = login_handle if isinstance(login_handle, LoginHandle) else LoginHandle(login_handle)
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM native_authenticators
                WHERE issuer_id = ? AND login_handle = ?
                """,
                (issuer_id, handle.value),
            ).fetchone()
            return None if row is None else self._authenticator_from_row(row)

    def update_native_password_hash(
        self,
        authenticator_id: str,
        *,
        expected_credential_revision: int,
        password_hash_phc: str,
    ) -> NativeAuthenticator:
        if (
            isinstance(expected_credential_revision, bool)
            or not isinstance(expected_credential_revision, int)
            or expected_credential_revision < 1
        ):
            raise ContractError("expected_credential_revision debe ser entero positivo")
        if not isinstance(password_hash_phc, str) or not password_hash_phc.startswith("$argon2id$v=19$"):
            raise ContractError("password_hash_phc debe ser PHC Argon2id")
        with self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE native_authenticators
                SET password_hash_phc = ?, credential_revision = credential_revision + 1,
                    updated_at = ?
                WHERE authenticator_id = ? AND credential_revision = ?
                  AND status = 'ACTIVE'
                """,
                (
                    password_hash_phc,
                    _utc_text(datetime.now(timezone.utc), "updated_at"),
                    authenticator_id,
                    expected_credential_revision,
                ),
            )
            if cursor.rowcount != 1:
                exists = connection.execute(
                    "SELECT 1 FROM native_authenticators WHERE authenticator_id = ?",
                    (authenticator_id,),
                ).fetchone()
                if exists is None:
                    raise ContractError("autenticador nativo no encontrado")
                raise ConcurrencyError("revisión obsoleta o autenticador no activo")
            row = connection.execute(
                "SELECT * FROM native_authenticators WHERE authenticator_id = ?",
                (authenticator_id,),
            ).fetchone()
            return self._authenticator_from_row(row)

    def create_native_authentication_proof(
        self, proof: NativeAuthenticationProof
    ) -> NativeAuthenticationProof:
        if not isinstance(proof, NativeAuthenticationProof):
            raise ContractError("proof debe ser NativeAuthenticationProof")
        if proof.status is not NativeAuthenticationProofStatus.PENDING:
            raise ContractError("solo se pueden persistir proofs PENDING")
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO native_authentication_proofs (
                        proof_id, reference_digest, issuer_id, native_subject,
                        authenticator_id, credential_revision, authenticated_at,
                        expires_at, audience, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        proof.proof_id,
                        proof.reference_digest,
                        proof.issuer_id,
                        proof.native_subject.value,
                        proof.authenticator_id,
                        proof.credential_revision,
                        _utc_text(proof.authenticated_at, "authenticated_at"),
                        _utc_text(proof.expires_at, "expires_at"),
                        proof.audience,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM native_authentication_proofs WHERE proof_id = ?",
                    (proof.proof_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError("proof nativo no pudo releerse")
                return self._proof_from_row(row)
        except sqlite3.IntegrityError as exc:
            raise IdentityConflictError(
                "proof duplicado o autenticador inactivo/revisión no vigente"
            ) from exc

    def consume_native_authentication_proof(
        self,
        reference: NativeProofReference,
        *,
        expected_audience: str,
        consumed_at: datetime,
    ) -> NativeAuthenticationProof | None:
        if not isinstance(reference, NativeProofReference):
            raise ContractError("reference debe ser NativeProofReference")
        if not isinstance(expected_audience, str) or not expected_audience:
            raise ContractError("expected_audience debe ser no vacío")
        now = _utc_text(consumed_at, "consumed_at")
        with self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE native_authentication_proofs
                SET status = 'CONSUMED'
                WHERE reference_digest = ? AND audience = ? AND status = 'PENDING'
                  AND expires_at > ? AND authenticated_at <= ?
                  AND EXISTS (
                      SELECT 1 FROM native_authenticators AS a
                      WHERE a.authenticator_id = native_authentication_proofs.authenticator_id
                        AND a.issuer_id = native_authentication_proofs.issuer_id
                        AND a.native_subject = native_authentication_proofs.native_subject
                        AND a.credential_revision = native_authentication_proofs.credential_revision
                        AND a.status = 'ACTIVE'
                  )
                """,
                (reference.digest, expected_audience, now, now),
            )
            if cursor.rowcount == 1:
                row = connection.execute(
                    "SELECT * FROM native_authentication_proofs WHERE reference_digest = ?",
                    (reference.digest,),
                ).fetchone()
                return self._proof_from_row(row)

            # Persist terminal outcomes for a matching proof; wrong audience is non-destructive.
            connection.execute(
                """
                UPDATE native_authentication_proofs SET status = 'EXPIRED'
                WHERE reference_digest = ? AND status = 'PENDING' AND expires_at <= ?
                """,
                (reference.digest, now),
            )
            connection.execute(
                """
                UPDATE native_authentication_proofs SET status = 'REVOKED'
                WHERE reference_digest = ? AND status = 'PENDING' AND audience = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM native_authenticators AS a
                      WHERE a.authenticator_id = native_authentication_proofs.authenticator_id
                        AND a.issuer_id = native_authentication_proofs.issuer_id
                        AND a.native_subject = native_authentication_proofs.native_subject
                        AND a.credential_revision = native_authentication_proofs.credential_revision
                        AND a.status = 'ACTIVE'
                  )
                """,
                (reference.digest, expected_audience),
            )
            return None
