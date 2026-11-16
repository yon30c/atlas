"""Comandos de consola para administrar conversaciones locales."""

from atlas.application.conversation_manager import ConversationManager
from atlas.assistant.local_console import LocalConsoleRequestFactory
from atlas.core.errors import ContractError, NotFoundError


class ConversationConsoleCommands:
    """Traduce comandos de consola a casos de uso del ConversationManager."""

    def __init__(self, manager: ConversationManager, request_factory: LocalConsoleRequestFactory) -> None:
        self._manager = manager
        self._request_factory = request_factory

    def handle(self, content: str) -> str | None:
        command, _, argument = content.strip().partition(" ")
        command = command.casefold()
        argument = argument.strip()
        try:
            if command == "/new":
                created = self._manager.create(argument or "Nueva conversación")
                self._request_factory.set_conversation_id(created.conversation_id)
                return f"Conversación nueva: {created.title} ({created.conversation_id})"
            if command == "/conversations":
                conversations = self._manager.list(include_closed=argument == "--all")
                if not conversations:
                    return "No hay conversaciones."
                active = self._manager.active()
                lines = ["Conversaciones:"]
                for item in conversations:
                    marker = "*" if active and item.conversation_id == active.conversation_id else " "
                    lines.append(f"{marker} {item.title} [{item.status.value}] {item.conversation_id}")
                return "\n".join(lines)
            if command == "/use":
                if not argument:
                    return "Uso: /use <conversation_id>"
                selected = self._manager.select(argument)
                self._request_factory.set_conversation_id(selected.conversation_id)
                return f"Conversación activa: {selected.title}"
            if command == "/rename":
                if not argument:
                    return "Uso: /rename <nuevo título>"
                renamed = self._manager.rename_active(argument)
                return f"Conversación renombrada: {renamed.title}"
            if command == "/close":
                closed = self._manager.close_active()
                active = self._manager.active()
                if active is None:
                    raise ContractError("no se pudo crear la conversación siguiente")
                self._request_factory.set_conversation_id(active.conversation_id)
                return f"Conversación cerrada: {closed.title}. Se inició una nueva."
        except (ContractError, NotFoundError) as exc:
            return f"No se pudo ejecutar el comando: {exc}"
        return None
