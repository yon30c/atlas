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
from atlas.memory.forget import ForgetClosure, ForgetTarget


class VerifiedForgetAuthorization(Protocol):
    """Evidencia ya verificada/consumida por CAM y OwnerDecisionVerifier.

    Solo el adaptador de CAM puede producir este objeto tras verificar una
    decisión directa, no delegable y de un solo uso del propietario. La
    autoridad de consistencia vuelve a comprobar el vínculo exacto de campos;
    este protocolo no implementa ni sustituye al emisor/verificador confiable.
    """

    @property
    def decision_id(self) -> str: ...

    @property
    def request_id(self) -> str: ...

    @property
    def actor_identity_id(self) -> str: ...

    @property
    def subject_user_id(self) -> str: ...

    @property
    def memory_id(self) -> str: ...

    @property
    def owner_id(self) -> str: ...


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
    """Capacidad bearer opaca; no contiene referencias a datos o handles internos."""

    read_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.read_id, str) or not self.read_id.strip():
            raise ContractError("read_id debe ser una capacidad no vacía")


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

    def begin_forget(
        self,
        target: ForgetTarget,
        authorization: VerifiedForgetAuthorization,
        idempotency_key: str,
        now: datetime,
    ) -> ForgetClosure | None:
        """Cierra atómicamente admisiones y avanza fencing para toda la Memory.

        Requiere autorización directa del propietario ya verificada y consumida
        por CAM. Debe serializarse con admit_read, conservar la operación por
        idempotencia y capturar todas las admisiones/rutas previas. Nunca
        confirma supresión mientras una admisión siga UNRESOLVED.
        """

    def reconcile_forget(self, operation_id: str) -> ForgetClosure | None:
        """Devuelve CLOSING hasta verificar terminalidad de todas las lecturas.

        SUPPRESSED solo significa que ninguna admisión previa puede emitir más;
        no significa eliminación física ni permite marcar versiones forgotten.
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
    ) -> tuple[ReadAdmission, ...] | None:
        """Enumera admisiones aún no terminales; None indica operación desconocida."""

    def reconcile(self, operation_id: str) -> ReconciliationResult | None:
        """Devuelve None si la operación no existe; si existe, informa evidencia verificable."""


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
