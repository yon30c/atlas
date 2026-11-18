"""SQLite adapter for canonical Workspace registry records."""

from datetime import datetime, timezone
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import WorkspaceRecord, WorkspaceStatus


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SQLiteWorkspaceRegistryRepository:
    """Stores workspace ownership and scope.

    Association reads/creation and lifecycle transitions use separate adapters.
    The repository never resolves root_ref to a filesystem path.
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
    def _required(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip() or value.strip() != value:
            raise ContractError(f"{field} debe ser texto no vacío y normalizado")
        return value

    @staticmethod
    def _next_revision(expected_revision: int, new_revision: int) -> None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ContractError("expected_revision debe ser un entero positivo")
        if new_revision != expected_revision + 1:
            raise ContractError("la nueva revisión debe ser expected_revision + 1")

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        key = self._required(workspace_id, "workspace_id")
        with self._read_connection() as connection:
            row = connection.execute(
                """SELECT workspace_id, owner_user_id, project_id, environment_id,
                          root_ref, status, revision
                   FROM atlas_workspaces WHERE workspace_id = ?""",
                (key,),
            ).fetchone()
        return None if row is None else self._workspace(row)

    def create_workspace(self, workspace: WorkspaceRecord) -> None:
        if not isinstance(workspace, WorkspaceRecord):
            raise ContractError("workspace debe ser WorkspaceRecord")
        now = _now_text()
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """INSERT INTO atlas_workspaces
                       (workspace_id, owner_user_id, project_id, environment_id,
                        root_ref, status, revision, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        workspace.workspace_id, workspace.owner_user_id,
                        workspace.project_id, workspace.environment_id,
                        workspace.root_ref, workspace.status.value,
                        workspace.revision, now, now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "workspace duplicado o owner, Project/Environment o asociación inexistente"
            ) from exc

    def update_workspace(
        self,
        workspace: WorkspaceRecord,
        *,
        expected_revision: int,
    ) -> None:
        if not isinstance(workspace, WorkspaceRecord):
            raise ContractError("workspace debe ser WorkspaceRecord")
        self._next_revision(expected_revision, workspace.revision)
        with self._write_connection() as connection:
            cursor = connection.execute(
                """UPDATE atlas_workspaces
                   SET status = ?, revision = ?, updated_at = ?
                   WHERE workspace_id = ? AND owner_user_id = ?
                     AND project_id = ? AND environment_id = ?
                     AND root_ref = ? AND revision = ?""",
                (
                    workspace.status.value, workspace.revision, _now_text(),
                    workspace.workspace_id, workspace.owner_user_id,
                    workspace.project_id, workspace.environment_id,
                    workspace.root_ref, expected_revision,
                ),
            )
            if cursor.rowcount == 1:
                return
            row = connection.execute(
                "SELECT revision FROM atlas_workspaces WHERE workspace_id = ?",
                (workspace.workspace_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("workspace canónico no encontrado")
            if row["revision"] != expected_revision:
                raise ConcurrencyError("la revisión del workspace cambió")
            raise ContractError("owner, scope y root_ref del workspace son inmutables")

    def list_workspaces_by_owner(self, owner_user_id: str) -> tuple[WorkspaceRecord, ...]:
        owner = self._required(owner_user_id, "owner_user_id")
        with self._read_connection() as connection:
            rows = connection.execute(
                """SELECT workspace_id, owner_user_id, project_id, environment_id,
                          root_ref, status, revision
                   FROM atlas_workspaces WHERE owner_user_id = ?
                   ORDER BY workspace_id""",
                (owner,),
            ).fetchall()
        return tuple(self._workspace(row) for row in rows)
