"""Orquestador de aplicación que conecta entrada local y servicios Atlas."""

from typing import Callable, Protocol

from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
)
from atlas.core.errors import ContractError


class RequestFactory(Protocol):
    """Construye solicitudes con identidad y contexto explícitos."""

    def create(self, content: str) -> AssistantRequest:
        """Crea una solicitud a partir del contenido del usuario."""


class AssistantProcessor(Protocol):
    """Procesa solicitudes sin exponer capacidades del proveedor LLM."""

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Genera una respuesta completa."""

    def respond_streaming(
        self,
        request: AssistantRequest,
        on_token: Callable[[str], None],
    ) -> AssistantResponse:
        """Genera una respuesta y emite fragmentos conforme llegan."""


class AtlasCore:
    """Coordina la creación de solicitudes y el procesamiento conversacional.

    AtlasCore es una fachada de aplicación. No concede permisos, no ejecuta
    herramientas y no permite que el modelo acceda directamente a sistemas.
    """

    def __init__(
        self,
        request_factory: RequestFactory,
        assistant: AssistantProcessor,
    ) -> None:
        if not callable(getattr(request_factory, "create", None)):
            raise ContractError("request_factory debe implementar create(content)")
        if not callable(getattr(assistant, "respond", None)):
            raise ContractError("assistant debe implementar respond(request)")
        if not callable(getattr(assistant, "respond_streaming", None)):
            raise ContractError(
                "assistant debe implementar respond_streaming(request, on_token)"
            )
        self._request_factory = request_factory
        self._assistant = assistant

    def respond(self, content: str) -> AssistantResponse:
        """Crea el contexto de la solicitud y devuelve la respuesta correlacionada."""
        request = self._create_request(content)
        response = self._assistant.respond(request)
        return self._validate_response(request, response)

    def respond_streaming(
        self,
        content: str,
        on_token: Callable[[str], None],
    ) -> AssistantResponse:
        """Coordina una respuesta en streaming sin acoplar la consola al servicio."""
        if not callable(on_token):
            raise ContractError("on_token debe ser invocable")
        request = self._create_request(content)
        response = self._assistant.respond_streaming(request, on_token)
        return self._validate_response(request, response)

    def _create_request(self, content: str) -> AssistantRequest:
        if not isinstance(content, str) or not content.strip():
            raise ContractError("content debe ser una cadena no vacía")
        request = self._request_factory.create(content)
        if not isinstance(request, AssistantRequest):
            raise ContractError("request_factory debe devolver AssistantRequest")
        return request

    @staticmethod
    def _validate_response(
        request: AssistantRequest,
        response: object,
    ) -> AssistantResponse:
        if not isinstance(response, AssistantResponse):
            raise ContractError("assistant debe devolver AssistantResponse")
        if response.request_id != request.request_id:
            raise ContractError("la respuesta no corresponde a la solicitud")
        if response.context != request.context:
            raise ContractError("el contexto de respuesta no corresponde a la solicitud")
        if not isinstance(response.kind, AssistantResponseKind):
            raise ContractError("la respuesta tiene un tipo no válido")
        return response
