"""Fábricas de composición para casos de uso de Atlas."""

from atlas.adapters.ollama_interpreter import OllamaIntentInterpreter
from atlas.assistant.request_planner import AssistantRequestPlanner
from atlas.core.errors import ContractError
from atlas.ports.llm import LLMProvider


def build_request_planner(
    provider: LLMProvider,
    model: str = "gemma4:e2b",
) -> AssistantRequestPlanner:
    """Compone el planificador con el intérprete Ollama y un proveedor existente.

    El proveedor se inyecta para reutilizar configuración y transporte. Esta
    fábrica no inicia Ollama, no modifica el runtime conversacional y no ejecuta
    capacidades.
    """
    if not callable(getattr(provider, "generate", None)):
        raise ContractError("provider debe implementar generate(request)")
    if not isinstance(model, str) or not model.strip():
        raise ContractError("model debe ser una cadena no vacía")

    interpreter = OllamaIntentInterpreter(
        provider=provider,
        model=model.strip(),
    )
    return AssistantRequestPlanner(interpreter=interpreter)
