"""Frontera de lectura autorizada y entrega protegida de memoria."""

from datetime import datetime, timedelta

from atlas.authorization.memory_service import MemoryAuthorizationService
from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.core.context import OperationContext
from atlas.memory.consistency import (
    DeliveryRouteSet,
    EgressReceipt,
    ReadAdmissionStatus,
    ReconciliationResult,
)
from atlas.memory.models import MemoryClassification, MemoryId, MemoryVersionId
from atlas.ports.clock import Clock
from atlas.ports.protected_memory_read import (
    ProtectedEgressPort,
    ProtectedMemoryContentPort,
    ProtectedMemoryRead,
    ReadConsistencyAuthorityPort,
)


class MemoryGatewayService:
    """Coordina CAM, admisión, lectura condicional y egress protegido.

    El Gateway nunca devuelve MemoryVersion ni contenido crudo. Devuelve un
    lease opaco que solo puede utilizarse mediante los métodos de emisión y
    finalización de esta frontera.
    """

    def __init__(
        self,
        authorization: MemoryAuthorizationService,
        content_port: ProtectedMemoryContentPort,
        consistency_authority: ReadConsistencyAuthorityPort,
        egress: ProtectedEgressPort,
        routes: DeliveryRouteSet,
        clock: Clock,
    ) -> None:
        self._authorization = authorization
        self._content = content_port
        self._authority = consistency_authority
        self._egress = egress
        self._routes = routes
        self._clock = clock

    @staticmethod
    def _valid_utc(value: object) -> bool:
        return (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() == timedelta(0)
        )

    @staticmethod
    def _valid_handle(handle: object, admission: object, snapshot: object) -> bool:
        if handle is None:
            return False
        classification = getattr(handle, "classification", None)
        handle_id = getattr(handle, "handle_id", None)
        return (
            getattr(handle, "admission_id", None) == admission.admission_id
            and getattr(handle, "memory_id", None) == admission.target.memory_id
            and getattr(handle, "version_id", None) == admission.target.version_id
            and isinstance(classification, MemoryClassification)
            and classification is snapshot.classification
            and classification is not MemoryClassification.RESTRICTED
            and isinstance(handle_id, str)
            and bool(handle_id.strip())
        )

    def _finish_empty_admission(self, admission, operation_id: str) -> None:
        """Cierra una admisión que no llegó a abrir ninguna entrega."""
        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return
            for endpoint_id in admission.route_ids:
                receipt = self._egress.finish(
                    admission, operation_id, endpoint_id, 0, now
                )
                if receipt is None or not self._authority.record_endpoint_ack(receipt):
                    return
            self._authority.reconcile(operation_id)
        except Exception:
            # La admisión queda pendiente y recuperable; nunca se presume terminal.
            return

    def get_version(
        self,
        context: OperationContext,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> ProtectedMemoryRead | None:
        """Abre una lectura protegida sin devolver el contenido al llamador."""
        if (
            not isinstance(context, OperationContext)
            or not isinstance(memory_id, str)
            or not memory_id.strip()
            or not isinstance(version_id, str)
            or not version_id.strip()
            or not isinstance(self._routes, DeliveryRouteSet)
        ):
            return None

        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return None
            result = self._authorization.authorize_read(
                context, memory_id, now, version_id
            )
            if (
                not isinstance(result, AuthorizationResult)
                or result.decision is not AuthorizationDecision.ALLOW
            ):
                return None

            snapshot = result.snapshot
            if (
                snapshot.memory_id != memory_id
                or snapshot.version_id != version_id
                or snapshot.actor_identity_id != context.actor.identity_id
                or snapshot.request_id != context.request_id
                or snapshot.action != "memory.read"
            ):
                return None

            admission_now = self._clock.now()
            if not self._valid_utc(admission_now):
                return None
            if (
                snapshot.grant_expires_at is not None
                and admission_now >= snapshot.grant_expires_at
            ):
                return None
            admission = self._authority.admit_read(
                snapshot, self._routes, admission_now
            )
            if admission is None:
                return None
            operation_id = f"read:{admission.admission_id}"

            if admission.status is not ReadAdmissionStatus.ADMITTED:
                # Una admisión preexistente/activa no se puede cerrar como vacía.
                return None
            if (
                admission.snapshot_id != snapshot.snapshot_id
                or admission.target.memory_id != memory_id
                or admission.target.version_id != version_id
                or admission.target.owner_id != snapshot.owner_id
                or admission.target.scope != snapshot.scope
                or admission.route_ids != self._routes.route_ids
            ):
                self._finish_empty_admission(admission, operation_id)
                return None

            try:
                handle = self._content.read_version_if_admitted(snapshot, admission)
            except Exception:
                self._finish_empty_admission(admission, operation_id)
                return None
            if not self._valid_handle(handle, admission, snapshot):
                self._finish_empty_admission(admission, operation_id)
                return None

            try:
                return ProtectedMemoryRead(
                    snapshot=snapshot,
                    admission=admission,
                    handle=handle,
                    operation_id=operation_id,
                )
            except Exception:
                self._finish_empty_admission(admission, operation_id)
                return None
        except Exception:
            return None

    def emit_version(
        self,
        read: ProtectedMemoryRead,
        endpoint_id: str,
        emission_id: str,
        sequence: int,
    ) -> EgressReceipt | None:
        """Compromete una unidad en el último punto controlado de entrega."""
        if not isinstance(read, ProtectedMemoryRead):
            return None
        if endpoint_id not in read.admission.route_ids:
            return None
        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return None
            expires_at = read.snapshot.grant_expires_at
            if expires_at is not None and now >= expires_at:
                return None
            return self._egress.commit_and_emit(
                read.admission,
                read.handle,
                endpoint_id,
                emission_id,
                sequence,
                now,
            )
        except Exception:
            return None

    def finish_version(
        self,
        read: ProtectedMemoryRead,
        endpoint_id: str,
        final_sequence: int,
    ) -> bool:
        """Registra la finalización verificable de un endpoint de entrega."""
        if not isinstance(read, ProtectedMemoryRead):
            return False
        if endpoint_id not in read.admission.route_ids:
            return False
        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return False
            receipt = self._egress.finish(
                read.admission,
                read.operation_id,
                endpoint_id,
                final_sequence,
                now,
            )
            if receipt is None:
                return False
            return self._authority.record_endpoint_ack(receipt)
        except Exception:
            return False

    def reconcile_version(
        self, read: ProtectedMemoryRead
    ) -> ReconciliationResult | None:
        """Revisa si todos los endpoints finalizaron; no fuerza terminalidad."""
        if not isinstance(read, ProtectedMemoryRead):
            return None
        try:
            return self._authority.reconcile(read.operation_id)
        except Exception:
            return None
