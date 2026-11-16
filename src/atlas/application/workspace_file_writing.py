"""Caso de uso para preparar y confirmar escrituras de workspace."""

from atlas.assistant.workspace_write import (
    WorkspaceRecoveryAssessment,
    WorkspaceWriteCommit,
    WorkspaceWriteStage,
)
from atlas.core.errors import ContractError
from atlas.ports.workspace_write import WorkspaceFileWriter


class WorkspaceFileWritingService:
    """Coordina staging/commit y verifica el binding de los resultados."""

    def __init__(self, writer: WorkspaceFileWriter) -> None:
        if not all(callable(getattr(writer, name, None)) for name in (
            "stage_write", "commit_write", "assess_recovery"
        )):
            raise ContractError("writer no implementa el contrato de escritura controlada")
        self._writer = writer

    def stage(
        self, workspace_id: str, path: str, content: str,
        operation_id: str, expected_sha256: str | None = None,
    ) -> WorkspaceWriteStage:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        if not isinstance(path, str) or not path.strip():
            raise ContractError("path debe ser texto no vacío")
        if not isinstance(content, str):
            raise ContractError("content debe ser texto")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser texto no vacío")
        result = self._writer.stage_write(
            workspace_id, path, content, operation_id, expected_sha256
        )
        if not isinstance(result, WorkspaceWriteStage):
            raise ContractError("writer debe devolver WorkspaceWriteStage")
        if (
            result.workspace_id != workspace_id
            or result.path != path
            or result.operation_id != operation_id
        ):
            raise ContractError("el staging no corresponde a la solicitud")
        return result

    def commit(self, workspace_id: str, operation_id: str) -> WorkspaceWriteCommit:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser texto no vacío")
        result = self._writer.commit_write(workspace_id, operation_id)
        if not isinstance(result, WorkspaceWriteCommit):
            raise ContractError("writer debe devolver WorkspaceWriteCommit")
        if result.workspace_id != workspace_id or result.operation_id != operation_id:
            raise ContractError("el commit no corresponde a la solicitud")
        if not result.committed:
            raise ContractError("el writer no confirmó el commit")
        return result

    def assess_recovery(
        self, workspace_id: str, operation_id: str
    ) -> WorkspaceRecoveryAssessment:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser texto no vacío")
        result = self._writer.assess_recovery(workspace_id, operation_id)
        if not isinstance(result, WorkspaceRecoveryAssessment):
            raise ContractError("writer debe devolver WorkspaceRecoveryAssessment")
        if result.workspace_id != workspace_id or result.operation_id != operation_id:
            raise ContractError("la evaluación no corresponde a la solicitud")
        return result
