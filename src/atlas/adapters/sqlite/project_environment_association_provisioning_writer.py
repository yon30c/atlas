"""Narrow persistence writer for the offline association provisioning flow.

This adapter is intentionally not attached to a general Unit of Work or
exported from the SQLite package. Only the dedicated offline entrypoint
should construct it after validating the host execution boundary.
"""

from contextlib import contextmanager
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.core.project_environment_association_provisioning import (
    ProjectEnvironmentAssociationProvisioningProvenance,
    ProjectEnvironmentAssociationProvisioningRequest,
)
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

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.unit_of_work() as unit:
                yield unit._connection_for(self._database)

    def create_association(
        self,
        request: ProjectEnvironmentAssociationProvisioningRequest,
        provenance: ProjectEnvironmentAssociationProvisioningProvenance,
    ) -> ProjectEnvironmentAssociation:
        if not isinstance(request, ProjectEnvironmentAssociationProvisioningRequest):
            raise ContractError("request debe ser ProjectEnvironmentAssociationProvisioningRequest")
        if not isinstance(provenance, ProjectEnvironmentAssociationProvisioningProvenance):
            raise ContractError(
                "provenance debe ser ProjectEnvironmentAssociationProvisioningProvenance"
            )
        association = ProjectEnvironmentAssociation(
            request.project_id,
            request.environment_id,
            ProjectEnvironmentStatus.ACTIVE,
            revision=1,
        )
        occurred_text = provenance.occurred_at.isoformat(timespec="microseconds")

        try:
            with self._write_connection() as connection:
                existing = connection.execute(
                    """SELECT event_id, project_id, environment_id, reason
                       FROM atlas_project_environment_provisioning_events
                       WHERE operation_id = ?""",
                    (request.operation_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["project_id"] != request.project_id
                        or existing["environment_id"] != request.environment_id
                        or existing["reason"] != request.reason
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
                        provenance.event_id, request.operation_id,
                        request.project_id, request.environment_id, request.reason,
                        provenance.real_uid, provenance.effective_uid,
                        provenance.terminal_id, occurred_text,
                    ),
                )
                connection.execute(
                    """INSERT INTO atlas_project_environments (
                        project_id, environment_id, status, revision,
                        created_at, updated_at, provisioning_event_id
                    ) VALUES (?, ?, 'active', 1, ?, ?, ?)""",
                    (
                        request.project_id, request.environment_id,
                        occurred_text, occurred_text, provenance.event_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError(
                "aprovisionamiento duplicado, inválido o sin Project/Environment canónico"
            ) from exc
        return association
