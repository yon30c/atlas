"""SQLite adapter for canonical Project/Environment association records."""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


class SQLiteProjectEnvironmentAssociationRepository:
    """Read canonical associations; creation and lifecycle writes are separate capabilities."""

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
