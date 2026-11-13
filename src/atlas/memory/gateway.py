"""Frontera de lectura autorizada para versiones de memoria."""

from atlas.authorization.memory_service import MemoryAuthorizationService
from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.core.context import OperationContext
from atlas.memory.models import (
    MemoryClassification,
    MemoryId,
    MemoryVersion,
    MemoryVersionId,
    MemoryVersionStatus,
)
from atlas.ports.clock import Clock
from atlas.ports.memory_content import MemoryVersionContentPort


class MemoryGatewayService:
    """Aplica CAM antes de recuperar contenido de una versión.

    Esta implementación cubre la lectura versionada. Las operaciones de
    enumeración y propuestas permanecen en el puerto MemoryGateway y se
    implementarán en sus fases correspondientes.
    """

    def __init__(
        self,
        authorization: MemoryAuthorizationService,
        content_port: MemoryVersionContentPort,
        clock: Clock,
    ) -> None:
        self._authorization = authorization
        self._content = content_port
        self._clock = clock

    def get_version(
        self,
        context: OperationContext,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> MemoryVersion | None:
        """Devuelve contenido solo tras ALLOW para memoria y versión exactas.

        None representa tanto denegación como ausencia/no disponibilidad para
        evitar que esta frontera revele la existencia de recursos protegidos.
        """
        if (
            not isinstance(context, OperationContext)
            or not isinstance(memory_id, str)
            or not memory_id.strip()
            or not isinstance(version_id, str)
            or not version_id.strip()
        ):
            return None

        try:
            now = self._clock.now()
            decision = self._authorization.authorize_read(
                context,
                memory_id,
                now,
                version_id,
            )
            if (
                not isinstance(decision, AuthorizationResult)
                or decision.decision is not AuthorizationDecision.ALLOW
            ):
                return None

            version = self._content.get_version_content(memory_id, version_id)
            if not isinstance(version, MemoryVersion):
                return None
            if version.memory_id != memory_id or version.version_id != version_id:
                return None
            if version.status is not MemoryVersionStatus.APPROVED:
                return None
            if version.classification is MemoryClassification.RESTRICTED:
                return None
            return version
        except Exception:
            return None
