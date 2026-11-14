"""Frontera de lectura autorizada y entrega protegida de memoria."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets
from threading import RLock

from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.memory.context import MemoryRequestContext
from atlas.memory.consistency import (
    AuthorizationSnapshot,
    DeliveryRouteSet,
    EgressReceipt,
    ReadAdmission,
    ReadAdmissionStatus,
    ReconciliationResult,
)
from atlas.memory.models import MemoryClassification, MemoryId, MemoryVersionId
from atlas.ports.clock import Clock
from atlas.ports.memory_authorization import MemoryAuthorizationPort
from atlas.ports.protected_memory_read import (
    ProtectedMemoryContentPort,
    ProtectedMemoryRead,
    ProtectedContentHandle,
    ProtectedMemoryConsistencyPort,
)


@dataclass(frozen=True, slots=True)
class _ProtectedReadSession:
    snapshot: AuthorizationSnapshot
    admission: ReadAdmission
    handle: ProtectedContentHandle
    operation_id: str


class MemoryGatewayService:
    """Coordina CAM, admisión, lectura condicional y egress protegido.

    El Gateway nunca devuelve MemoryVersion ni contenido crudo. Devuelve un
    lease opaco que solo puede utilizarse mediante los métodos de emisión y
    finalización de esta frontera.
    """

    def __init__(
        self,
        authorization: MemoryAuthorizationPort,
        content_port: ProtectedMemoryContentPort,
        consistency: ProtectedMemoryConsistencyPort,
        routes: DeliveryRouteSet,
        clock: Clock,
    ) -> None:
        self._authorization = authorization
        self._content = content_port
        self._consistency = consistency
        self._routes = routes
        self._clock = clock
        # Solo el Gateway conserva referencias internas al snapshot/admisión/handle.
        # El registro es local al proceso y no sustituye la recuperación durable.
        self._read_sessions: dict[str, _ProtectedReadSession] = {}
        self._read_sessions_lock = RLock()

    @staticmethod
    def _valid_utc(value: object) -> bool:
        return (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() == timedelta(0)
        )

    @staticmethod
    def _valid_handle(
        handle: object, admission: ReadAdmission, snapshot: AuthorizationSnapshot
    ) -> bool:
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
                receipt = self._consistency.finish(
                    admission, operation_id, endpoint_id, 0, now
                )
                if receipt is None or not self._consistency.record_endpoint_ack(receipt):
                    return
            self._consistency.reconcile(operation_id)
        except Exception:
            # La admisión queda pendiente y recuperable; nunca se presume terminal.
            return

    def get_version(
        self,
        context: MemoryRequestContext,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> ProtectedMemoryRead | None:
        """Abre una lectura protegida sin devolver el contenido al llamador."""
        if (
            not isinstance(context, MemoryRequestContext)
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
                or snapshot.actor_identity_id != context.actor_id
                or snapshot.revisions.identity_revision.revision != context.actor_revision
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
            admission = self._consistency.admit_read(
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
                read_id = secrets.token_urlsafe(32)
                session = _ProtectedReadSession(
                    snapshot=snapshot,
                    admission=admission,
                    handle=handle,
                    operation_id=operation_id,
                )
                with self._read_sessions_lock:
                    if read_id in self._read_sessions:
                        self._finish_empty_admission(admission, operation_id)
                        return None
                    self._read_sessions[read_id] = session
                return ProtectedMemoryRead(read_id=read_id)
            except Exception:
                self._finish_empty_admission(admission, operation_id)
                return None
        except Exception:
            return None

    def _resolve_read(self, read: ProtectedMemoryRead) -> _ProtectedReadSession | None:
        if not isinstance(read, ProtectedMemoryRead):
            return None
        with self._read_sessions_lock:
            return self._read_sessions.get(read.read_id)

    def emit_version(
        self,
        read: ProtectedMemoryRead,
        endpoint_id: str,
        emission_id: str,
        sequence: int,
    ) -> EgressReceipt | None:
        """Compromete una unidad en el último punto controlado de entrega."""
        session = self._resolve_read(read)
        if (
            session is None
            or not isinstance(endpoint_id, str)
            or not endpoint_id.strip()
            or not isinstance(emission_id, str)
            or not emission_id.strip()
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
        ):
            return None
        if endpoint_id not in session.admission.route_ids:
            return None
        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return None
            expires_at = session.snapshot.grant_expires_at
            if expires_at is not None and now >= expires_at:
                return None
            return self._consistency.commit_and_emit(
                session.admission,
                session.handle,
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
        session = self._resolve_read(read)
        if (
            session is None
            or not isinstance(endpoint_id, str)
            or not endpoint_id.strip()
            or isinstance(final_sequence, bool)
            or not isinstance(final_sequence, int)
            or final_sequence < 0
        ):
            return False
        if endpoint_id not in session.admission.route_ids:
            return False
        try:
            now = self._clock.now()
            if not self._valid_utc(now):
                return False
            receipt = self._consistency.finish(
                session.admission,
                session.operation_id,
                endpoint_id,
                final_sequence,
                now,
            )
            if receipt is None:
                return False
            return self._consistency.record_endpoint_ack(receipt)
        except Exception:
            return False

    def reconcile_version(
        self, read: ProtectedMemoryRead
    ) -> ReconciliationResult | None:
        """Revisa si todos los endpoints finalizaron; no fuerza terminalidad."""
        session = self._resolve_read(read)
        if session is None:
            return None
        try:
            result = self._consistency.reconcile(session.operation_id)
            if (
                result is not None
                and session.admission.admission_id in result.resolved_admission_ids
            ):
                with self._read_sessions_lock:
                    current = self._read_sessions.get(read.read_id)
                    if current is session:
                        self._read_sessions.pop(read.read_id, None)
            return result
        except Exception:
            return None
