"""Contratos de staging, commit y recuperación de escrituras de workspace."""

from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError


class WorkspaceWriteState(str, Enum):
    STAGED = "staged"
    COMMITTING = "committing"
    COMMITTED = "committed"


class WorkspaceRecoveryStatus(str, Enum):
    STAGED_READY = "staged_ready"
    COMMIT_CONFIRMED = "commit_confirmed"
    COMMIT_NOT_APPLIED = "commit_not_applied"
    COMMITTED = "committed"
    CONFLICT = "conflict"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class WorkspaceWriteStage:
    workspace_id: str
    operation_id: str
    path: str
    content_sha256: str
    size_bytes: int
    expected_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ContractError("operation_id debe ser texto no vacío")
        if not isinstance(self.path, str) or not self.path.strip():
            raise ContractError("path debe ser texto no vacío")
        if not isinstance(self.content_sha256, str) or len(self.content_sha256) != 64:
            raise ContractError("content_sha256 debe ser SHA-256 hexadecimal")
        if any(c not in "0123456789abcdef" for c in self.content_sha256):
            raise ContractError("content_sha256 debe ser SHA-256 hexadecimal")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractError("size_bytes debe ser un entero no negativo")
        if self.expected_sha256 is not None and (
            not isinstance(self.expected_sha256, str)
            or len(self.expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.expected_sha256)
        ):
            raise ContractError("expected_sha256 debe ser SHA-256 hexadecimal o None")


@dataclass(frozen=True, slots=True)
class WorkspaceWriteCommit:
    workspace_id: str
    operation_id: str
    path: str
    content_sha256: str
    size_bytes: int
    committed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.committed, bool):
            raise ContractError("committed debe ser booleano")
        if not self.workspace_id or not self.operation_id or not self.path:
            raise ContractError("workspace_id, operation_id y path son obligatorios")
        if len(self.content_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.content_sha256):
            raise ContractError("content_sha256 debe ser SHA-256 hexadecimal")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractError("size_bytes debe ser un entero no negativo")


@dataclass(frozen=True, slots=True)
class WorkspaceRecoveryAssessment:
    workspace_id: str
    operation_id: str
    status: WorkspaceRecoveryStatus
    path: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.workspace_id or not self.operation_id:
            raise ContractError("workspace_id y operation_id son obligatorios")
        if not isinstance(self.status, WorkspaceRecoveryStatus):
            raise ContractError("status debe ser WorkspaceRecoveryStatus")
        if self.path is not None and not isinstance(self.path, str):
            raise ContractError("path debe ser texto o None")
        if self.detail is not None and not isinstance(self.detail, str):
            raise ContractError("detail debe ser texto o None")
