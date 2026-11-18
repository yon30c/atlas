"""SQLite adapter for canonical Project/Environment association records."""

from datetime import datetime, timezone
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SQLiteProjectEnvironmentAssociationRepository:
    """Read/create canonical associations; it cannot transition their lifecycle."""

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
    def _required(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip() or value.strip() != value:
            raise ContractError(f"{field} debe ser texto no vacío y normalizado")
        return value

    @staticmethod
    def _association(row: sqlite3.Row) -> ProjectEnvironmentAssociation:
        return ProjectEnvironmentAssociation(
            project_id=ProjectId(row["project_id"]),
            environment_id=EnvironmentId(row["environment_id"]),
            status=ProjectEnvironmentStatus(row["status"]),
            revision=row["revision"],
        )

    def get_association(
        self, project_id: ProjectId, environment_id: EnvironmentId
    ) -> ProjectEnvironmentAssociation | None:
        project = self._required(project_id, "project_id")
        environment = self._required(environment_id, "environment_id")
        with self._read_connection() as connection:
            row = connection.execute(
                """SELECT project_id, environment_id, status, revision
                   FROM atlas_project_environments
                   WHERE project_id = ? AND environment_id = ?""",
                (project, environment),
            ).fetchone()
        return None if row is None else self._association(row)

    def create_association(self, association: ProjectEnvironmentAssociation) -> None:
        if not isinstance(association, ProjectEnvironmentAssociation):
            raise ContractError("association debe ser ProjectEnvironmentAssociation")
        now = _now_text()
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """INSERT INTO atlas_project_environments
                       (project_id, environment_id, status, revision, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        association.project_id, association.environment_id,
                        association.status.value, association.revision, now, now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "asociación duplicada o Project/Environment inexistente"
            ) from exc
