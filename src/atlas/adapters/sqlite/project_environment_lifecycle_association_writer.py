"""Internal SQLite writer for authorized Project/Environment lifecycle transitions."""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWork
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.workspace.models import ProjectEnvironmentAssociation


class SQLiteProjectEnvironmentLifecycleAssociationWriter:
    """CAS writer bound to one active local-authority UoW.

    This adapter performs persistence only. Authorization belongs to the
    lifecycle application service and must be checked in the same UoW.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        unit_of_work: SQLiteLocalAuthorityUnitOfWork,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if not isinstance(unit_of_work, SQLiteLocalAuthorityUnitOfWork):
            raise ContractError("unit_of_work debe ser SQLiteLocalAuthorityUnitOfWork")
        self._database = database
        self._unit_of_work = unit_of_work

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        unit = self._unit_of_work
        if (
            not unit._active
            or unit._database is not self._database
            or unit._connection is None
            or not unit._connection.in_transaction
        ):
            raise ContractError("la UoW lifecycle no está activa en esta base de datos")
        yield unit._connection

    @staticmethod
    def _required(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip() or value.strip() != value:
            raise ContractError(f"{field} debe ser texto no vacío y normalizado")
        return value

    def update_association(
        self,
        association: ProjectEnvironmentAssociation,
        *,
        expected_revision: int,
        lifecycle_event_id: str,
    ) -> None:
        if not isinstance(association, ProjectEnvironmentAssociation):
            raise ContractError("association debe ser ProjectEnvironmentAssociation")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if association.revision != expected_revision + 1:
            raise ContractError("la nueva revisión debe ser expected_revision + 1")
        event_id = self._required(lifecycle_event_id, "lifecycle_event_id")
        with self._write_connection() as connection:
            cursor = connection.execute(
                """UPDATE atlas_project_environments
                   SET status = ?, revision = ?,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'),
                       last_lifecycle_event_id = ?
                   WHERE project_id = ? AND environment_id = ? AND revision = ?""",
                (
                    association.status.value, association.revision, event_id,
                    association.project_id, association.environment_id, expected_revision,
                ),
            )
            if cursor.rowcount == 1:
                return
            row = connection.execute(
                """SELECT revision FROM atlas_project_environments
                   WHERE project_id = ? AND environment_id = ?""",
                (association.project_id, association.environment_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("asociación Project/Environment no encontrada")
            raise ConcurrencyError("la revisión de la asociación cambió")
