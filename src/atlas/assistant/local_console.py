"""Composición mínima del asistente para una sesión de consola local."""

from getpass import getuser
from uuid import uuid4

from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponseKind,
)
from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.ports.clock import Clock


class LocalConsoleRequestFactory:
    """Construye solicitudes ligadas a la cuenta local del sistema."""

    def __init__(self, clock: Clock, user_id: str | None = None) -> None:
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock debe implementar now()")

        resolved_user = getuser() if user_id is None else user_id
        if not isinstance(resolved_user, str) or not resolved_user.strip():
            raise ContractError("user_id local debe ser una cadena no vacía")

        self._clock = clock
        self._user_id = resolved_user.strip()
        self._conversation_id = str(uuid4())

    def create(self, content: str) -> AssistantRequest:
        """Crea una solicitud con identidad y contexto locales explícitos."""
        now = self._clock.now()
        request_id = str(uuid4())
        local_user_id = f"local:{self._user_id}"
        actor = Identity(
            identity_id=f"local-user:{self._user_id}",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        context = OperationContext(
            request_id=request_id,
            correlation_id=request_id,
            actor=actor,
            user_id=local_user_id,
            origin="console",
            delegation=None,
            project_id=None,
            environment="local",
            purpose="local_conversation",
            classification="internal",
            created_at=now,
        )
        return AssistantRequest(
            request_id=request_id,
            context=context,
            content=content,
            received_at=now,
            conversation_id=self._conversation_id,
        )


class LocalModeResponseGenerator:
    """Respuesta honesta mientras Atlas no tenga un proveedor LLM."""

    def generate(
        self,
        request: AssistantRequest,
    ) -> tuple[AssistantResponseKind, str]:
        """Indica que el mensaje llegó, sin simular comprensión generativa."""
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")

        return (
            AssistantResponseKind.INFORMATIONAL,
            "He recibido tu mensaje. Todavía no tengo conectado un modelo de "
            "lenguaje, así que aún no puedo interpretar solicitudes ni "
            "ejecutar tareas. La sesión local y su contexto ya están "
            "funcionando.",
        )
