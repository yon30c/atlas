"""SQLite persistence adapter for Grant renewal requests."""

from contextlib import contextmanager
from datetime import datetime
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.authorization.models import GrantRenewalRequest, RenewalStatus
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.ports.grant_renewals import GrantRenewalRepository


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


class SQLiteGrantRenewalRepository(GrantRenewalRepository):
    """Persists renewal requests with immutable binding and versioned decisions."""

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
    def _from_row(row: sqlite3.Row) -> GrantRenewalRequest:
        try:
            return GrantRenewalRequest(
                renewal_id=row["renewal_id"],
                grant_id=row["grant_id"],
                owner_user_id=row["owner_user_id"],
                subject_identity_id=row["subject_identity_id"],
                requested_by_identity_id=row["requested_by_identity_id"],
                current_expires_at=datetime.fromisoformat(row["current_expires_at"]),
                proposed_expires_at=datetime.fromisoformat(row["proposed_expires_at"]),
                requested_at=datetime.fromisoformat(row["requested_at"]),
                status=RenewalStatus(row["status"]),
                decided_at=(
                    None if row["decided_at"] is None
                    else datetime.fromisoformat(row["decided_at"])
                ),
                decided_by_user_id=row["decided_by_user_id"],
                version=row["version"],
                grant_revision=row["grant_revision"],
                delegation_id=row["delegation_id"],
                delegation_revision=row["delegation_revision"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro de renovación SQLite corrupto o inválido") from exc

    @staticmethod
    def _values(request: GrantRenewalRequest) -> tuple[object, ...]:
        if not isinstance(request, GrantRenewalRequest):
            raise ContractError("request debe ser GrantRenewalRequest")
        return (
            request.renewal_id,
            request.grant_id,
            request.owner_user_id,
            request.subject_identity_id,
            request.requested_by_identity_id,
            _timestamp(request.current_expires_at),
            _timestamp(request.proposed_expires_at),
            _timestamp(request.requested_at),
            request.status.value,
            None if request.decided_at is None else _timestamp(request.decided_at),
            request.decided_by_user_id,
            request.version,
            request.grant_revision,
            request.delegation_id,
            request.delegation_revision,
        )

    def create(self, request: GrantRenewalRequest) -> None:
        values = self._values(request)
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO authorization_grant_renewals (
                        renewal_id, grant_id, owner_user_id, subject_identity_id,
                        requested_by_identity_id, current_expires_at,
                        proposed_expires_at, requested_at, status, decided_at,
                        decided_by_user_id, version, grant_revision,
                        delegation_id, delegation_revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "No se pudo crear la solicitud de renovación por conflicto de integridad"
            ) from exc

    def get(self, renewal_id: str) -> GrantRenewalRequest | None:
        if not isinstance(renewal_id, str) or not renewal_id.strip():
            raise ContractError("renewal_id debe ser una cadena no vacía")
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM authorization_grant_renewals WHERE renewal_id = ?",
                (renewal_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, request: GrantRenewalRequest) -> None:
        values = self._values(request)
        if request.version < 2:
            raise ContractError("una actualización debe incrementar la versión")
        if not self.update_if_version(request, request.version - 1):
            with self._read_connection() as connection:
                row = connection.execute(
                    "SELECT renewal_id FROM authorization_grant_renewals WHERE renewal_id = ?",
                    (request.renewal_id,),
                ).fetchone()
            if row is None:
                raise NotFoundError("Solicitud de renovación no encontrada")
            raise ConcurrencyError("la versión de la solicitud cambió")

    def update_if_version(
        self,
        request: GrantRenewalRequest,
        expected_version: int,
    ) -> bool:
        values = self._values(request)
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise ContractError("expected_version debe ser un entero positivo")
        try:
            with self._write_connection() as connection:
                current = connection.execute(
                    """
                    SELECT version FROM authorization_grant_renewals
                    WHERE renewal_id = ?
                    """,
                    (values[0],),
                ).fetchone()
                # A stale or missing record is a normal CAS conflict, not a
                # malformed update. Check it before validating the proposed
                # next version so callers can safely handle stale requests.
                if current is None or current["version"] != expected_version:
                    return False
                if request.version != expected_version + 1:
                    raise ContractError("la nueva versión debe ser expected_version + 1")
                cursor = connection.execute(
                    """
                    UPDATE authorization_grant_renewals
                    SET status = ?, decided_at = ?, decided_by_user_id = ?,
                        version = ?
                    WHERE renewal_id = ? AND version = ?
                    """,
                    (
                        values[8], values[9], values[10], values[11],
                        values[0], expected_version,
                    ),
                )
                return cursor.rowcount == 1
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "La actualización viola la integridad de la solicitud"
            ) from exc

    def list_by_grant(self, grant_id: str) -> tuple[GrantRenewalRequest, ...]:
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ContractError("grant_id debe ser una cadena no vacía")
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM authorization_grant_renewals
                WHERE grant_id = ?
                ORDER BY requested_at, renewal_id
                """,
                (grant_id,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)
