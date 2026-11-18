"""SQLite adapter for immutable Project/Environment lifecycle events."""

from contextlib import contextmanager
from datetime import datetime
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.core.project_environment_lifecycle import ProjectEnvironmentLifecycleEvent
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentStatus


class SQLiteProjectEnvironmentLifecycleLedger:
    """Persists and reads lifecycle facts, optionally inside a caller-owned UoW.

    Appending an event without its matching association transition cannot
    commit: V26's deferred foreign keys require both writes in one transaction.
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
    def _from_row(row: sqlite3.Row) -> ProjectEnvironmentLifecycleEvent:
        try:
            return ProjectEnvironmentLifecycleEvent(
                event_id=row["event_id"],
                project_id=ProjectId(row["project_id"]),
                environment_id=EnvironmentId(row["environment_id"]),
                previous_status=ProjectEnvironmentStatus(row["previous_status"]),
                new_status=ProjectEnvironmentStatus(row["new_status"]),
                previous_revision=row["previous_revision"],
                new_revision=row["new_revision"],
                actor_user_id=row["actor_user_id"],
                actor_identity_id=row["actor_identity_id"],
                verified_identity_context_id=row["verified_identity_context_id"],
                request_id=row["request_id"],
                correlation_id=row["correlation_id"],
                reason=row["reason"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
        except (KeyError, TypeError, ValueError, ContractError) as exc:
            raise ContractError(
                "registro de lifecycle SQLite corrupto o inválido"
            ) from exc

    def append_event(self, event: ProjectEnvironmentLifecycleEvent) -> None:
        if not isinstance(event, ProjectEnvironmentLifecycleEvent):
            raise ContractError(
                "event debe ser ProjectEnvironmentLifecycleEvent"
            )
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO atlas_project_environment_lifecycle_events (
                        event_id, project_id, environment_id,
                        previous_status, new_status,
                        previous_revision, new_revision,
                        actor_user_id, actor_identity_id,
                        verified_identity_context_id,
                        request_id, correlation_id, reason, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.project_id,
                        event.environment_id,
                        event.previous_status.value,
                        event.new_status.value,
                        event.previous_revision,
                        event.new_revision,
                        event.actor_user_id,
                        event.actor_identity_id,
                        event.verified_identity_context_id,
                        event.request_id,
                        event.correlation_id,
                        event.reason,
                        event.occurred_at.isoformat(timespec="microseconds"),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "No se pudo registrar el evento lifecycle por conflicto de integridad"
            ) from exc

    def list_events(
        self, project_id: str, environment_id: str
    ) -> tuple[ProjectEnvironmentLifecycleEvent, ...]:
        project = self._required(project_id, "project_id")
        environment = self._required(environment_id, "environment_id")
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, project_id, environment_id,
                       previous_status, new_status,
                       previous_revision, new_revision,
                       actor_user_id, actor_identity_id,
                       verified_identity_context_id,
                       request_id, correlation_id, reason, occurred_at
                FROM atlas_project_environment_lifecycle_events
                WHERE project_id = ? AND environment_id = ?
                ORDER BY new_revision ASC
                """,
                (project, environment),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)
