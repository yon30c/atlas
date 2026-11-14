"""Servicio de aplicación para procesar solicitudes conversacionales."""

from typing import Callable, Protocol

from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
)
from atlas.core.errors import ContractError
from atlas.ports.clock import Clock


class AssistantResponseGenerator(Protocol):
    """Frontera intercambiable para generar contenido de respuesta."""

    def generate(
        self,
        request: AssistantRequest,
    ) -> tuple[AssistantResponseKind, str]:
        """Produce el tipo y contenido de una respuesta, sin ejecutarla."""


class AssistantService:
    """Coordina solicitudes y construye respuestas correlacionadas."""

    def __init__(
        self,
        response_generator: AssistantResponseGenerator,
        clock: Clock,
    ) -> None:
        if not callable(getattr(response_generator, "generate", None)):
            raise ContractError(
                "response_generator debe implementar generate(request)"
            )
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock debe implementar now()")
        self._response_generator = response_generator
        self._clock = clock

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Procesa una solicitud sin conceder permisos ni ejecutar acciones."""
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")
        generated = self._response_generator.generate(request)
        return self._build_response(request, generated)

    def respond_streaming(
        self,
        request: AssistantRequest,
        on_token: Callable[[str], None],
    ) -> AssistantResponse:
        """Emite fragmentos conforme llegan y devuelve la respuesta final."""
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")
        if not callable(on_token):
            raise ContractError("on_token debe ser invocable")
        streaming_generator = getattr(
            self._response_generator, "generate_streaming", None
        )
        if callable(streaming_generator):
            generated = streaming_generator(request, on_token)
        else:
            generated = self._response_generator.generate(request)
            if (
                isinstance(generated, tuple)
                and len(generated) == 2
                and isinstance(generated[1], str)
            ):
                on_token(generated[1])
        return self._build_response(request, generated)

    def _build_response(
        self,
        request: AssistantRequest,
        generated: object,
    ) -> AssistantResponse:
        if not isinstance(generated, tuple) or len(generated) != 2:
            raise ContractError(
                "generate debe devolver (AssistantResponseKind, contenido)"
            )
        kind, content = generated
        if not isinstance(kind, AssistantResponseKind):
            raise ContractError(
                "el generador debe devolver un AssistantResponseKind válido"
            )
        if not isinstance(content, str) or not content.strip():
            raise ContractError(
                "el generador debe devolver contenido no vacío"
            )
        return AssistantResponse(
            request_id=request.request_id,
            context=request.context,
            kind=kind,
            content=content,
            created_at=self._clock.now(),
        )
