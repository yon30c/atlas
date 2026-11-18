"""Narrow persistence writer for the offline association provisioning flow.

This adapter is intentionally not attached to a general Unit of Work or
exported from the SQLite package. Only the dedicated offline composition
should construct it after validating the host execution boundary.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Iterator
from uuid import UUID

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


class SQLiteProjectEnvironmentAssociationProvisioningWriter:
    """Atomically persist an immutable provisioning event and its association."""

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

    @staticmethod
    def _uuid4(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise ContractError(f"{field} debe ser UUIDv4")
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ContractError(f"{field} debe ser UUIDv4") from exc
        if parsed.version != 4 or str(parsed) != value:
            raise ContractError(f"{field} debe ser UUIDv4 canónico")
        return value

    @staticmethod
    def _text(value: object, field: str, maximum: int) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ContractError(f"{field} debe ser texto normalizado sin controles")
        return value

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.unit_of_work() as unit:
                yield unit._connection_for(self._database)

    def create_association(
        self,
        association: ProjectEnvironmentAssociation,
        *,
        event_id: str,
        operation_id: str,
        reason: str,
        real_uid: int,
        effective_uid: int,
        terminal_id: str,
        occurred_at: datetime,
    ) -> ProjectEnvironmentAssociation:
        if not isinstance(association, ProjectEnvironmentAssociation):
            raise ContractError("association debe ser ProjectEnvironmentAssociation")
        if association.status is not ProjectEnvironmentStatus.ACTIVE or association.revision != 1:
            raise ContractError("el aprovisionamiento inicial solo crea ACTIVE/revision 1")
        event_id = self._uuid4(event_id, "event_id")
        operation_id = self._uuid4(operation_id, "operation_id")
        reason = self._text(reason, "reason", 500)
        terminal_id = self._text(terminal_id, "terminal_id", 256)
        if isinstance(real_uid, bool) or not isinstance(real_uid, int) or real_uid <= 0:
            raise ContractError("real_uid debe ser un entero positivo")
        if isinstance(effective_uid, bool) or not isinstance(effective_uid, int) or effective_uid != 0:
            raise ContractError("effective_uid debe ser exactamente 0")
        if (
            not isinstance(occurred_at, datetime)
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() != timezone.utc.utcoffset(occurred_at)
        ):
            raise ContractError("occurred_at debe ser datetime UTC")
        occurred_text = occurred_at.astimezone(timezone.utc).isoformat(timespec="microseconds")

        try:
            with self._write_connection() as connection:
                existing = connection.execute(
                    """SELECT event_id, project_id, environment_id, reason
                       FROM atlas_project_environment_provisioning_events
                       WHERE operation_id = ?""",
                    (operation_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["project_id"] != association.project_id
                        or existing["environment_id"] != association.environment_id
                        or existing["reason"] != reason
                    ):
                        raise ContractError("operation_id ya fue usado con otra intención")
                    row = connection.execute(
                        """SELECT 1 FROM atlas_project_environments
                           WHERE provisioning_event_id = ?""",
                        (existing["event_id"],),
                    ).fetchone()
                    if row is None:
                        raise ContractError("registro idempotente incompleto; operación denegada")
                    return association

                connection.execute(
                    """INSERT INTO atlas_project_environment_provisioning_events (
                        event_id, operation_id, project_id, environment_id, reason,
                        real_uid, effective_uid, terminal_id, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, operation_id, association.project_id,
                        association.environment_id, reason, real_uid,
                        effective_uid, terminal_id, occurred_text,
                    ),
                )
                connection.execute(
                    """INSERT INTO atlas_project_environments (
                        project_id, environment_id, status, revision,
                        created_at, updated_at, provisioning_event_id
                    ) VALUES (?, ?, 'active', 1, ?, ?, ?)""",
                    (
                        association.project_id, association.environment_id,
                        occurred_text, occurred_text, event_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "aprovisionamiento duplicado, inválido o sin Project/Environment canónico"
            ) from exc
        return association
