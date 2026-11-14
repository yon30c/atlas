"""Puente entre solicitudes conversacionales y el proveedor local Ollama."""

from typing import Callable

from atlas.adapters.ollama import OllamaError
from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponseKind,
    ConversationMessageRole,
)
from atlas.core.errors import ContractError
from atlas.ports.llm import (
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)


ATLAS_SYSTEM_PROMPT = (
    "You are Atlas, a local conversational assistant. "
    "Respond naturally in the language used by the user. "
    "Be clear, practical, and honest about uncertainty. "
    "You only generate conversational text. You have no tools, "
    "cannot access files or systems, and cannot execute actions. "
    "Never claim that you performed an operation."
)


class OllamaResponseGenerator:
    """Adapta el puerto LLM al contrato que consume AssistantService."""

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "gemma4:e2b",
        *,
        system_prompt: str = ATLAS_SYSTEM_PROMPT,
        temperature: float | None = 0.2,
        max_tokens: int | None = 512,
    ) -> None:
        if not callable(getattr(provider, "generate", None)):
            raise ContractError("provider debe implementar generate(request)")
        if not isinstance(model, str) or not model.strip():
            raise ContractError("model debe ser una cadena no vacía")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ContractError("system_prompt debe ser una cadena no vacía")
        self._provider = provider
        self._model = model.strip()
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _build_request(self, request: AssistantRequest) -> LLMRequest:
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")

        role_mapping = {
            ConversationMessageRole.USER: LLMMessageRole.USER,
            ConversationMessageRole.ASSISTANT: LLMMessageRole.ASSISTANT,
        }
        messages = [LLMMessage(LLMMessageRole.SYSTEM, self._system_prompt)]
        messages.extend(
            LLMMessage(role_mapping[item.role], item.content)
            for item in request.history
        )
        messages.append(LLMMessage(LLMMessageRole.USER, request.content))

        return LLMRequest(
            model=self._model,
            messages=tuple(messages),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

    def generate(
        self,
        request: AssistantRequest,
    ) -> tuple[AssistantResponseKind, str]:
        """Genera texto local sin exponer herramientas ni autoridad operativa."""
        llm_request = self._build_request(request)
        try:
            response = self._provider.generate(llm_request)
        except OllamaError:
            return self._provider_error()
        return self._map_response(response)

    def generate_streaming(
        self,
        request: AssistantRequest,
        on_token: Callable[[str], None],
    ) -> tuple[AssistantResponseKind, str]:
        """Genera texto progresivamente cuando el proveedor soporta streaming."""
        if not callable(on_token):
            raise ContractError("on_token debe ser invocable")
        llm_request = self._build_request(request)
        try:
            stream_method = getattr(self._provider, "generate_stream", None)
            if callable(stream_method):
                response = stream_method(llm_request, on_token)
            else:
                response = self._provider.generate(llm_request)
                if isinstance(response, LLMResponse):
                    on_token(response.content)
        except OllamaError:
            return self._provider_error()
        return self._map_response(response)

    @staticmethod
    def _provider_error() -> tuple[AssistantResponseKind, str]:
        return (
            AssistantResponseKind.ERROR,
            "No pude obtener una respuesta del modelo local. Comprueba "
            "que Ollama esté disponible y que el modelo configurado "
            "esté instalado.",
        )

    @staticmethod
    def _map_response(
        response: object,
    ) -> tuple[AssistantResponseKind, str]:
        if not isinstance(response, LLMResponse):
            raise ContractError("provider debe devolver una LLMResponse")
        return AssistantResponseKind.INFORMATIONAL, response.content
