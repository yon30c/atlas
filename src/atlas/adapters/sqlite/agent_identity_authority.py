"""SQLite persistence adapter for canonical AGENT identities."""

from contextlib import contextmanager
from datetime import datetime, timezone
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
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.user_identity import validate_canonical_uuid4
from atlas.ports.agent_identity_authority import AgentIdentityAuthorityPort


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SQLiteAgentIdentityAuthority(AgentIdentityAuthorityPort):
    """The sole local issuer of canonical Identity(AGENT) records.

    AGENT identities are stored in identity_records with user_id=NULL.
    This adapter never creates or resolves atlas_users rows and has no
    authentication, binding, delegation, recovery, or authorization duties.
    """

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
    def _from_row(row: sqlite3.Row) -> CanonicalAgentIdentity:
        if row["identity_kind"] != IdentityKind.AGENT.value or row["user_id"] is not None:
            raise ContractError("el registro persistido no es una identidad AGENT canónica")
        return CanonicalAgentIdentity(
            identity=Identity(
                identity_id=row["identity_id"],
                kind=IdentityKind.AGENT,
                status=IdentityStatus(row["identity_status"]),
                revision=row["revision"],
            )
        )

    def create_agent(self) -> CanonicalAgentIdentity:
        """Generate and persist one canonical AGENT identity atomically."""
        identity_id = str(uuid4())
        now = _utc_now_text()
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status,
                        revision, created_at, updated_at, user_id
                    ) VALUES (?, 'agent', 'active', 1, ?, ?, NULL)
                    """,
                    (identity_id, now, now),
                )
                row = connection.execute(
                    """
                    SELECT identity_id, identity_kind, identity_status, revision, user_id
                    FROM identity_records
                    WHERE identity_id = ? AND identity_kind = 'agent'
                      AND user_id IS NULL
                    """,
                    (identity_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.DatabaseError(
                        "la creación canónica no pudo releer la identidad AGENT"
                    )
                return self._from_row(row)
        except sqlite3.IntegrityError as exc:
            # Never retry with a replacement identifier or overwrite an existing row.
            raise IdentityConflictError(
                "conflicto de unicidad o integridad al crear la identidad AGENT"
            ) from exc

    def get_agent_by_identity_id(
        self, identity_id: str
    ) -> CanonicalAgentIdentity | None:
        validate_canonical_uuid4(identity_id, "identity_id")
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT identity_id, identity_kind, identity_status, revision, user_id
                FROM identity_records
                WHERE identity_id = ? AND identity_kind = 'agent' AND user_id IS NULL
                """,
                (identity_id,),
            ).fetchone()
            return None if row is None else self._from_row(row)

    def update_agent_status(
        self,
        identity_id: str,
        *,
        expected_revision: int,
        status: IdentityStatus,
    ) -> CanonicalAgentIdentity:
        validate_canonical_uuid4(identity_id, "identity_id")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if not isinstance(status, IdentityStatus):
            raise ContractError("status debe ser IdentityStatus")

        with self._write_connection() as connection:
            row = connection.execute(
                """
                SELECT identity_id, identity_kind, identity_status, revision, user_id
                FROM identity_records
                WHERE identity_id = ? AND identity_kind = 'agent' AND user_id IS NULL
                """,
                (identity_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("identidad AGENT canónica no encontrada")
            current = self._from_row(row)
            if current.identity.revision != expected_revision:
                raise ConcurrencyError("revisión de identidad AGENT obsoleta")
            if (
                current.identity.status is IdentityStatus.REVOKED
                and status is not IdentityStatus.REVOKED
            ):
                raise ContractError("una identidad AGENT revocada es terminal")
            if current.identity.status is status:
                return current

            cursor = connection.execute(
                """
                UPDATE identity_records
                SET identity_status = ?, revision = revision + 1, updated_at = ?
                WHERE identity_id = ? AND identity_kind = 'agent'
                  AND user_id IS NULL AND revision = ?
                """,
                (status.value, _utc_now_text(), identity_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError(
                    "la identidad AGENT cambió durante la actualización"
                )
            updated = connection.execute(
                """
                SELECT identity_id, identity_kind, identity_status, revision, user_id
                FROM identity_records
                WHERE identity_id = ? AND identity_kind = 'agent' AND user_id IS NULL
                """,
                (identity_id,),
            ).fetchone()
            if updated is None:
                raise sqlite3.DatabaseError(
                    "la identidad AGENT desapareció durante una actualización"
                )
            return self._from_row(updated)
