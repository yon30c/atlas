"""Contexto conversacional acotado a la sesión actual de Atlas."""

from dataclasses import replace
from threading import RLock
from typing import Protocol

from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
    ConversationMessage,
    ConversationMessageRole,
)
from atlas.core.errors import ContractError


class ConversationHistoryStore(Protocol):
    """Almacenamiento intercambiable del historial por conversación."""

    def get_history(self, conversation_id: str) -> tuple[ConversationMessage, ...]:
        """Devuelve una instantánea inmutable del historial."""

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
    ) -> None:
        """Añade un turno completo de usuario y asistente."""


class InMemoryConversationHistory:
    """Historial en memoria, aislado por conversación y limitado por turnos."""

    def __init__(self, max_turns: int = 8) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 1:
            raise ContractError("max_turns debe ser un entero positivo")
        self._max_messages = max_turns * 2
        self._histories: dict[str, list[ConversationMessage]] = {}
        self._lock = RLock()

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ContractError("conversation_id debe ser una cadena no vacía")

    def get_history(self, conversation_id: str) -> tuple[ConversationMessage, ...]:
        self._validate_conversation_id(conversation_id)
        with self._lock:
            return tuple(self._histories.get(conversation_id, ()))

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
    ) -> None:
        self._validate_conversation_id(conversation_id)
        user_message = ConversationMessage(ConversationMessageRole.USER, user_content)
        assistant_message = ConversationMessage(
            ConversationMessageRole.ASSISTANT, assistant_content
        )
        with self._lock:
            history = self._histories.setdefault(conversation_id, [])
            history.extend((user_message, assistant_message))
            if len(history) > self._max_messages:
                del history[:-self._max_messages]


class ConversationContextProcessor:
    """Enriquece solicitudes con historial y persiste solo turnos exitosos."""

    def __init__(
        self,
        assistant: object,
        history_store: ConversationHistoryStore,
    ) -> None:
        if not callable(getattr(assistant, "respond", None)):
            raise ContractError("assistant debe implementar respond(request)")
        if not callable(getattr(assistant, "respond_streaming", None)):
            raise ContractError(
                "assistant debe implementar respond_streaming(request, on_token)"
            )
        if not callable(getattr(history_store, "get_history", None)) or not callable(
            getattr(history_store, "append_turn", None)
        ):
            raise ContractError(
                "history_store debe implementar get_history() y append_turn()"
            )
        self._assistant = assistant
        self._history_store = history_store

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        enriched_request = self._with_history(request)
        response = self._assistant.respond(enriched_request)
        self._commit_successful_turn(enriched_request, response)
        return response

    def respond_streaming(self, request, on_token) -> AssistantResponse:
        if not callable(on_token):
            raise ContractError("on_token debe ser invocable")
        enriched_request = self._with_history(request)
        response = self._assistant.respond_streaming(enriched_request, on_token)
        self._commit_successful_turn(enriched_request, response)
        return response

    def _with_history(self, request: AssistantRequest) -> AssistantRequest:
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")
        if request.conversation_id is None:
            raise ContractError("la solicitud requiere conversation_id")
        history = self._history_store.get_history(request.conversation_id)
        return replace(request, history=history)

    def _commit_successful_turn(
        self,
        request: AssistantRequest,
        response: object,
    ) -> None:
        if not isinstance(response, AssistantResponse):
            raise ContractError("assistant debe devolver AssistantResponse")
        if response.kind is AssistantResponseKind.ERROR:
            return
        self._history_store.append_turn(
            request.conversation_id,
            request.content,
            response.content,
        )
