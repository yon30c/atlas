"""Contexto conversacional y contratos de aplicación de Atlas."""

from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Callable, Protocol

from atlas.assistant.conversation import Conversation
from atlas.assistant.models import (
    AssistantRequest, AssistantResponse, AssistantResponseKind,
    ConversationMessage, ConversationMessageRole,
)
from atlas.core.errors import ContractError


class AssistantProcessor(Protocol):
    def respond(self, request: AssistantRequest) -> AssistantResponse: ...
    def respond_streaming(self, request: AssistantRequest, on_token: Callable[[str], None]) -> AssistantResponse: ...


class ConversationRepository(Protocol):
    def create(self, conversation: Conversation) -> Conversation: ...
    def get(self, conversation_id: str) -> Conversation | None: ...
    def list_conversations(self, *, include_closed: bool = False) -> tuple[Conversation, ...]: ...
    def rename(self, conversation_id: str, title: str, updated_at: datetime) -> Conversation: ...
    def close(self, conversation_id: str, updated_at: datetime) -> Conversation: ...
    def delete(self, conversation_id: str) -> None: ...
    def get_active_conversation(self) -> Conversation | None: ...
    def set_active_conversation(self, conversation_id: str) -> None: ...


class ConversationHistoryStore(Protocol):
    def get_history(self, conversation_id: str) -> tuple[ConversationMessage, ...]: ...
    def append_turn(self, conversation_id: str, user_content: str, assistant_content: str) -> None: ...


class InMemoryConversationHistory:
    """Historial aislado por conversación, limitado por turnos y caracteres."""

    _TRUNCATION_MARKER = "\n[...contenido histórico truncado...]"

    def __init__(self, max_turns: int = 8, max_message_chars: int = 2000) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 1:
            raise ContractError("max_turns debe ser un entero positivo")
        if isinstance(max_message_chars, bool) or not isinstance(max_message_chars, int) or max_message_chars <= len(self._TRUNCATION_MARKER):
            raise ContractError("max_message_chars debe ser un entero mayor que el marcador")
        self._max_messages = max_turns * 2
        self._max_message_chars = max_message_chars
        self._histories: dict[str, list[ConversationMessage]] = {}
        self._lock = RLock()

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ContractError("conversation_id debe ser una cadena no vacía")

    def _bound_content(self, content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            raise ContractError("el contenido histórico debe ser una cadena no vacía")
        if len(content) <= self._max_message_chars:
            return content
        return content[:self._max_message_chars - len(self._TRUNCATION_MARKER)] + self._TRUNCATION_MARKER

    def get_history(self, conversation_id: str) -> tuple[ConversationMessage, ...]:
        self._validate_conversation_id(conversation_id)
        with self._lock:
            return tuple(self._histories.get(conversation_id, ()))

    def append_turn(self, conversation_id: str, user_content: str, assistant_content: str) -> None:
        self._validate_conversation_id(conversation_id)
        user_message = ConversationMessage(ConversationMessageRole.USER, self._bound_content(user_content))
        assistant_message = ConversationMessage(ConversationMessageRole.ASSISTANT, self._bound_content(assistant_content))
        with self._lock:
            history = self._histories.setdefault(conversation_id, [])
            history.extend((user_message, assistant_message))
            if len(history) > self._max_messages:
                del history[:-self._max_messages]


class ConversationContextProcessor:
    """Proyecta historial durable al contexto acotado del modelo."""

    _TRUNCATION_MARKER = "\n[...contenido histórico truncado...]"

    def __init__(
        self, assistant: AssistantProcessor, history_store: ConversationHistoryStore,
        *, max_history_turns: int = 8, max_message_chars: int = 2000,
    ) -> None:
        if not callable(getattr(assistant, "respond", None)) or not callable(getattr(assistant, "respond_streaming", None)):
            raise ContractError("assistant debe implementar respond() y respond_streaming()")
        if not callable(getattr(history_store, "get_history", None)) or not callable(getattr(history_store, "append_turn", None)):
            raise ContractError("history_store debe implementar get_history() y append_turn()")
        if isinstance(max_history_turns, bool) or not isinstance(max_history_turns, int) or max_history_turns < 1:
            raise ContractError("max_history_turns debe ser un entero positivo")
        if isinstance(max_message_chars, bool) or not isinstance(max_message_chars, int) or max_message_chars <= len(self._TRUNCATION_MARKER):
            raise ContractError("max_message_chars debe superar el marcador de truncamiento")
        self._assistant = assistant
        self._history_store = history_store
        self._max_history_messages = max_history_turns * 2
        self._max_message_chars = max_message_chars

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        enriched = self._with_history(request)
        response = self._assistant.respond(enriched)
        self._commit_successful_turn(enriched, response)
        return response

    def respond_streaming(self, request: AssistantRequest, on_token: Callable[[str], None]) -> AssistantResponse:
        if not callable(on_token):
            raise ContractError("on_token debe ser invocable")
        enriched = self._with_history(request)
        response = self._assistant.respond_streaming(enriched, on_token)
        self._commit_successful_turn(enriched, response)
        return response

    def _with_history(self, request: AssistantRequest) -> AssistantRequest:
        if not isinstance(request, AssistantRequest):
            raise ContractError("request debe ser AssistantRequest")
        if request.conversation_id is None:
            raise ContractError("la solicitud requiere conversation_id")
        stored = self._history_store.get_history(request.conversation_id)
        history = tuple(
            ConversationMessage(message.role, self._bound_message_content(message.content))
            for message in stored[-self._max_history_messages:]
        )
        return replace(request, history=history)

    def _bound_message_content(self, content: str) -> str:
        if len(content) <= self._max_message_chars:
            return content
        return content[:self._max_message_chars - len(self._TRUNCATION_MARKER)] + self._TRUNCATION_MARKER

    def _commit_successful_turn(self, request: AssistantRequest, response: object) -> None:
        if not isinstance(response, AssistantResponse):
            raise ContractError("assistant debe devolver AssistantResponse")
        if response.request_id != request.request_id or response.context != request.context:
            raise ContractError("la respuesta no corresponde a la solicitud")
        if response.kind is AssistantResponseKind.ERROR:
            return
        if request.conversation_id is None:
            raise ContractError("la solicitud requiere conversation_id")
        self._history_store.append_turn(request.conversation_id, request.content, response.content)
