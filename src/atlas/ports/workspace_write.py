"""Puertos de escritura controlada de workspace."""

from typing import Protocol

from atlas.assistant.workspace_write import (
    WorkspaceRecoveryAssessment,
    WorkspaceWriteCommit,
    WorkspaceWriteStage,
)


class WorkspaceFileWriter(Protocol):
    """Escritura de archivo con staging durable y commit explícito."""

    def stage_write(
        self,
        workspace_id: str,
        path: str,
        content: str,
        operation_id: str,
        expected_sha256: str | None = None,
    ) -> WorkspaceWriteStage:
        """Prepara contenido sin modificar el destino final."""

    def commit_write(self, workspace_id: str, operation_id: str) -> WorkspaceWriteCommit:
        """Aplica una escritura previamente preparada y validada."""

    def assess_recovery(
        self, workspace_id: str, operation_id: str
    ) -> WorkspaceRecoveryAssessment:
        """Inspecciona el estado durable sin modificarlo."""
