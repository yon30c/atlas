"""Canonical SQLite sources for Project and Environment metadata."""

import sqlite3

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.memory.ports.metadata import EnvironmentMetadataPort, ProjectMetadataPort


class SQLiteProjectEnvironmentRepository(
    ProjectMetadataPort,
    EnvironmentMetadataPort,
):
    """Stores minimal canonical Project and Environment authority revisions.

    The repository is bound to one SQLiteDatabase instance. It deliberately
    exposes no delete operation: lifecycle changes are represented by status
    revisions and records remain available as authority tombstones.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _required_id(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} debe ser una cadena no vacía")
        return value

    def get_project(self, project_id: ProjectId) -> ProjectMetadata | None:
        key = self._required_id(project_id, "project_id")
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT project_id, status, revision FROM atlas_projects WHERE project_id = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return ProjectMetadata(
            project_id=ProjectId(row["project_id"]),
            status=row["status"],
            revision=row["revision"],
        )

    def create_project(self, project: ProjectMetadata) -> None:
        if not isinstance(project, ProjectMetadata):
            raise ContractError("project debe ser ProjectMetadata")
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                connection.execute(
                    """
                    INSERT INTO atlas_projects (project_id, status, revision)
                    VALUES (?, ?, ?)
                    """,
                    (project.project_id, project.status, project.revision),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("conflicto al crear el proyecto canónico") from exc

    def update_project(
        self,
        project: ProjectMetadata,
        *,
        expected_revision: int,
    ) -> None:
        if not isinstance(project, ProjectMetadata):
            raise ContractError("project debe ser ProjectMetadata")
        self._expected_next_revision(expected_revision, project.revision)
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            cursor = connection.execute(
                """
                UPDATE atlas_projects SET status = ?, revision = ?
                WHERE project_id = ? AND revision = ?
                """,
                (project.status, project.revision, project.project_id, expected_revision),
            )
            if cursor.rowcount == 1:
                return
            row = connection.execute(
                "SELECT revision FROM atlas_projects WHERE project_id = ?",
                (project.project_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("proyecto canónico no encontrado")
            raise ConcurrencyError("la revisión del proyecto cambió")

    def get_environment(
        self,
        environment_id: EnvironmentId,
    ) -> EnvironmentMetadata | None:
        key = self._required_id(environment_id, "environment_id")
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT environment_id, status, revision
                FROM atlas_environments WHERE environment_id = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return EnvironmentMetadata(
            environment_id=EnvironmentId(row["environment_id"]),
            status=row["status"],
            revision=row["revision"],
        )

    def create_environment(self, environment: EnvironmentMetadata) -> None:
        if not isinstance(environment, EnvironmentMetadata):
            raise ContractError("environment debe ser EnvironmentMetadata")
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                connection.execute(
                    """
                    INSERT INTO atlas_environments (environment_id, status, revision)
                    VALUES (?, ?, ?)
                    """,
                    (
                        environment.environment_id,
                        environment.status,
                        environment.revision,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("conflicto al crear el entorno canónico") from exc

    def update_environment(
        self,
        environment: EnvironmentMetadata,
        *,
        expected_revision: int,
    ) -> None:
        if not isinstance(environment, EnvironmentMetadata):
            raise ContractError("environment debe ser EnvironmentMetadata")
        self._expected_next_revision(expected_revision, environment.revision)
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            cursor = connection.execute(
                """
                UPDATE atlas_environments SET status = ?, revision = ?
                WHERE environment_id = ? AND revision = ?
                """,
                (
                    environment.status,
                    environment.revision,
                    environment.environment_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 1:
                return
            row = connection.execute(
                "SELECT revision FROM atlas_environments WHERE environment_id = ?",
                (environment.environment_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("entorno canónico no encontrado")
            raise ConcurrencyError("la revisión del entorno cambió")

    @staticmethod
    def _expected_next_revision(expected_revision: int, new_revision: int) -> None:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if new_revision != expected_revision + 1:
            raise ContractError("la nueva revisión debe ser expected_revision + 1")
