"""Puertos tipados para admisión y entrega protegida de memoria ME-03."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from atlas.memory.consistency import (
    AuthorizationInvalidation,
    AuthorizationSnapshot,
    DeliveryRouteSet,
    EgressReceipt,
    InvalidationReceipt,
    EndpointCompletionReceipt,
    EndpointDeliveryStatus,
    EndpointFenceReceipt,
    ReadAdmission,
    ReconciliationResult,
)
from atlas.memory.models import MemoryClassification


class ProtectedContentHandle(Protocol):
    """Handle interno no serializable; nunca expone el contenido a llamadores."""

    @property
    def handle_id(self) -> str: ...

    @property
    def admission_id(self) -> str: ...

    @property
    def memory_id(self) -> str: ...

    @property
    def version_id(self) -> str: ...

    @property
    def classification(self) -> MemoryClassification: ...


@dataclass(frozen=True, slots=True)
class ProtectedMemoryRead:
    """Lease opaco de lectura; no contiene ni expone MemoryVersion."""

    snapshot: AuthorizationSnapshot
    admission: ReadAdmission
    handle: ProtectedContentHandle
    operation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, AuthorizationSnapshot):
            raise ValueError("snapshot debe ser AuthorizationSnapshot")
        if not isinstance(self.admission, ReadAdmission):
            raise ValueError("admission debe ser ReadAdmission")
        if self.admission.snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("admission no corresponde al snapshot")
        if self.operation_id != f"read:{self.admission.admission_id}":
            raise ValueError("operation_id no corresponde a la admisión")
        target = self.admission.target
        if (
            getattr(self.handle, "admission_id", None) != self.admission.admission_id
            or getattr(self.handle, "memory_id", None) != target.memory_id
            or getattr(self.handle, "version_id", None) != target.version_id
            or getattr(self.handle, "classification", None) is not self.snapshot.classification
            or not getattr(self.handle, "handle_id", None)
        ):
            raise ValueError("handle no corresponde al objetivo/admisión autorizados")


class ProtectedMemoryContentPort(Protocol):
    """Recupera contenido solo para un snapshot y admisión exactos."""

    def read_version_if_admitted(
        self,
        snapshot: AuthorizationSnapshot,
        admission: ReadAdmission,
    ) -> ProtectedContentHandle | None:
        """Devuelve un handle interno o None; nunca aplica fallback por IDs."""


class ReadConsistencyAuthorityPort(Protocol):
    """Autoridad lógica única para admisiones, cierres e invalidaciones."""

    def admit_read(
        self,
        snapshot: AuthorizationSnapshot,
        routes: DeliveryRouteSet,
    ) -> ReadAdmission | None:
        """Registra durablemente una admisión o falla cerrada."""

    def begin_invalidation(
        self,
        invalidation: AuthorizationInvalidation,
    ) -> InvalidationReceipt | None:
        """Ordena la invalidación y el fencing antes de permitir nuevas emisiones."""

    def record_endpoint_ack(
        self,
        receipt: EndpointFenceReceipt | EndpointCompletionReceipt,
    ) -> bool:
        """Registra un acknowledgement correlacionado e idempotente."""

    def get_nonterminal_admissions(
        self,
        operation_id: str,
    ) -> tuple[ReadAdmission, ...]:
        """Enumera admisiones aún no terminales para la operación."""

    def reconcile(self, operation_id: str) -> ReconciliationResult:
        """Devuelve admisiones resueltas y no resueltas con evidencia verificable."""


class ProtectedEgressPort(Protocol):
    """Último punto controlado: compromiso y aceptación de emisión indivisibles."""

    def commit_and_emit(
        self,
        admission: ReadAdmission,
        handle: ProtectedContentHandle,
        endpoint_id: str,
        emission_id: str,
        sequence: int,
        now: datetime,
    ) -> EgressReceipt | None:
        """Acepta irrevocablemente una unidad solo si el fencing sigue vigente."""

    def finish(
        self,
        admission: ReadAdmission,
        operation_id: str,
        endpoint_id: str,
        final_sequence: int,
        now: datetime,
    ) -> EndpointCompletionReceipt | None:
        """Confirma finalización para la operación/admisión exacta."""

    def fence(
        self,
        admission: ReadAdmission,
        operation_id: str,
        endpoint_id: str,
        new_generation: int,
        now: datetime,
    ) -> EndpointFenceReceipt | None:
        """Confirma fencing para la operación y generación exactas."""

    def reconcile(
        self,
        admission: ReadAdmission,
        endpoint_id: str,
    ) -> EndpointDeliveryStatus:
        """Verifica el estado real del endpoint; timeout no equivale a fencing."""
