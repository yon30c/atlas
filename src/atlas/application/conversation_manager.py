"""Casos de uso para el ciclo de vida de conversaciones."""

from uuid import uuid4

from atlas.application.conversation import ConversationRepository
from atlas.assistant.conversation import Conversation, ConversationStatus
from atlas.core.errors import ContractError, NotFoundError
from atlas.ports.clock import Clock


class ConversationManager:
    """Coordina conversaciones sin depender de la consola ni del proveedor LLM."""

    def __init__(self, repository: ConversationRepository, clock: Clock) -> None:
        required = ("create", "get", "list_conversations", "rename", "close",
                    "delete", "get_active_conversation", "set_active_conversation")
        if any(not callable(getattr(repository, name, None)) for name in required):
            raise ContractError("repository no implementa ConversationRepository")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock debe implementar now()")
        self._repository = repository
        self._clock = clock

    def active(self) -> Conversation | None:
        return self._repository.get_active_conversation()

    def create(self, title: str = "Nueva conversación") -> Conversation:
        if not isinstance(title, str) or not title.strip():
            raise ContractError("title debe ser una cadena no vacía")
        now = self._clock.now()
        item = Conversation(
            conversation_id=str(uuid4()), title=title.strip(),
            status=ConversationStatus.ACTIVE, created_at=now, updated_at=now,
        )
        created = self._repository.create(item)
        self._repository.set_active_conversation(created.conversation_id)
        return created

    def list(self, *, include_closed: bool = False) -> tuple[Conversation, ...]:
        return self._repository.list_conversations(include_closed=include_closed)

    def select(self, conversation_id: str) -> Conversation:
        item = self._repository.get(conversation_id)
        if item is None or item.status is not ConversationStatus.ACTIVE:
            raise NotFoundError("conversación activa no encontrada")
        self._repository.set_active_conversation(conversation_id)
        return item

    def rename_active(self, title: str) -> Conversation:
        item = self.active()
        if item is None:
            raise NotFoundError("no hay una conversación activa")
        return self._repository.rename(item.conversation_id, title, self._clock.now())

    def close_active(self) -> Conversation:
        item = self.active()
        if item is None:
            raise NotFoundError("no hay una conversación activa")
        closed = self._repository.close(item.conversation_id, self._clock.now())
        self.create()
        return closed

    def delete(self, conversation_id: str) -> None:
        active = self.active()
        was_active = active is not None and active.conversation_id == conversation_id
        self._repository.delete(conversation_id)
        if was_active:
            self.create()
