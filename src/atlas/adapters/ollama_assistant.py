"""Puente entre solicitudes conversacionales y el proveedor local Ollama."""

from atlas.adapters.ollama import OllamaError
from atlas.assistant.models import AssistantRequest, AssistantResponseKind
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
        model: str,
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

    def generate(
        self,
        request: AssistantRequest,
    ) -> tuple[AssistantResponseKind, str]:
        """Genera texto local sin exponer herramientas ni autoridad operativa."""
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")

        llm_request = LLMRequest(
            model=self._model,
            messages=(
                LLMMessage(LLMMessageRole.SYSTEM, self._system_prompt),
                LLMMessage(LLMMessageRole.USER, request.content),
            ),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

        try:
            response = self._provider.generate(llm_request)
        except OllamaError:
            return (
                AssistantResponseKind.ERROR,
                "No pude obtener una respuesta del modelo local. Comprueba "
                "que Ollama esté disponible y que el modelo configurado "
                "esté instalado.",
            )

        if not isinstance(response, LLMResponse):
            raise ContractError("provider debe devolver una LLMResponse")

        return AssistantResponseKind.INFORMATIONAL, response.content
