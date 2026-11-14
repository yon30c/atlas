"""Contratos neutrales para proveedores locales de modelos de lenguaje."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError


class LLMMessageRole(str, Enum):
    """Roles conversacionales independientes del proveedor."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Mensaje individual que forma parte de una solicitud al modelo."""

    role: LLMMessageRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, LLMMessageRole):
            raise ContractError("role debe ser LLMMessageRole")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ContractError("content debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Solicitud portable que un adaptador traduce a su proveedor local."""

    model: str
    messages: tuple[LLMMessage, ...]
    temperature: float | None = None
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ContractError("model debe ser una cadena no vacía")
        if (
            not isinstance(self.messages, tuple)
            or not self.messages
            or any(not isinstance(item, LLMMessage) for item in self.messages)
        ):
            raise ContractError("messages debe ser una tupla no vacía de LLMMessage")
        if self.temperature is not None:
            if (
                isinstance(self.temperature, bool)
                or not isinstance(self.temperature, (int, float))
                or not 0 <= self.temperature <= 2
            ):
                raise ContractError("temperature debe estar entre 0 y 2")
        if self.max_tokens is not None:
            if (
                isinstance(self.max_tokens, bool)
                or not isinstance(self.max_tokens, int)
                or self.max_tokens <= 0
            ):
                raise ContractError("max_tokens debe ser un entero positivo")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Resultado textual devuelto por un proveedor, sin autoridad operativa."""

    provider: str
    model: str
    content: str
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("provider", "model", "content"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field_name} debe ser una cadena no vacía")
        if self.finish_reason is not None and (
            not isinstance(self.finish_reason, str) or not self.finish_reason.strip()
        ):
            raise ContractError("finish_reason debe ser None o una cadena no vacía")


class LLMProvider(Protocol):
    """Puerto que implementa cada adaptador de modelo local."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Genera texto; no ejecuta herramientas ni acciones del sistema."""
