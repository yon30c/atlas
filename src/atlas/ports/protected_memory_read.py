"""Puertos tipados para admisión y entrega protegida de memoria ME-03."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from atlas.core.errors import ContractError

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
    ReadAdmissionStatus,
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

    snapshot: AuthorizationSnapshot = field(repr=False)
    admission: ReadAdmission
    handle: ProtectedContentHandle = field(repr=False)
    operation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, AuthorizationSnapshot):
            raise ContractError("snapshot debe ser AuthorizationSnapshot")
        if not isinstance(self.admission, ReadAdmission):
            raise ContractError("admission debe ser ReadAdmission")
        if self.admission.snapshot_id != self.snapshot.snapshot_id:
            raise ContractError("admission no corresponde al snapshot")
        if self.admission.status not in (
            ReadAdmissionStatus.ADMITTED,
            ReadAdmissionStatus.ACTIVE,
        ):
            raise ContractError("la admisión no está abierta para entrega")
        if self.operation_id != f"read:{self.admission.admission_id}":
            raise ContractError("operation_id no corresponde a la admisión")
        target = self.admission.target
        if (
            getattr(self.handle, "admission_id", None) != self.admission.admission_id
            or getattr(self.handle, "memory_id", None) != target.memory_id
            or getattr(self.handle, "version_id", None) != target.version_id
            or target.owner_id != self.snapshot.owner_id
            or target.scope != self.snapshot.scope
            or not isinstance(getattr(self.handle, "classification", None), MemoryClassification)
            or self.handle.classification is not self.snapshot.classification
            or self.handle.classification is MemoryClassification.RESTRICTED
            or not isinstance(getattr(self.handle, "handle_id", None), str)
            or not self.handle.handle_id.strip()
        ):
            raise ContractError("handle no corresponde al objetivo/admisión autorizados")


class ProtectedMemoryContentPort(Protocol):
    """Recupera contenido solo para un snapshot y admisión exactos."""

    def read_version_if_admitted(
        self,
        snapshot: AuthorizationSnapshot,
        admission: ReadAdmission,
    ) -> ProtectedContentHandle | None:
        """Devuelve un handle interno o None; nunca aplica fallback por IDs.

        Debe comprobar de nuevo que snapshot y admisión siguen vigentes, que no
        hay supresión y que la creación del handle no puede escapar a una admisión
        cerrada. El handle no expone payload ni ofrece lectura fuera de egress.
        """


class ReadConsistencyAuthorityPort(Protocol):
    """Autoridad lógica única para admisiones, cierres e invalidaciones."""

    def admit_read(
        self,
        snapshot: AuthorizationSnapshot,
        routes: DeliveryRouteSet,
        now: datetime,
    ) -> ReadAdmission | None:
        """Registra admisión y operación read:{admission_id} de forma atómica.

        La autoridad debe comprobar supresión, revisiones actuales, generación y
        cobertura de rutas. Si falta cualquiera de esas evidencias, falla cerrado.
        """

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
        """Acepta irrevocablemente una unidad solo si el fencing sigue vigente.

        El último punto de entrega valida en cada unidad las revisiones actuales,
        generación, supresión y expiración de Grant usando tiempo confiable. La
        comprobación y la aceptación irreversible comparten el mismo orden lógico.
        """

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
