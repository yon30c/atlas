"""Comandos de consola para administrar conversaciones locales."""

from getpass import getpass

from atlas.adapters.sqlite.conversation_backup import ConversationBackup
from atlas.application.conversation_manager import ConversationManager
from atlas.assistant.local_console import LocalConsoleRequestFactory
from atlas.core.errors import ContractError, NotFoundError


class ConversationConsoleCommands:
    def __init__(
        self, manager: ConversationManager, request_factory: LocalConsoleRequestFactory,
        backup: ConversationBackup,
    ) -> None:
        self._manager = manager
        self._request_factory = request_factory
        self._backup = backup

    def handle(self, content: str) -> str | None:
        command, _, argument = content.strip().partition(" ")
        command, argument = command.casefold(), argument.strip()
        try:
            if command == "/new":
                item = self._manager.create(argument or "Nueva conversación")
                self._request_factory.set_conversation_id(item.conversation_id)
                return f"Conversación nueva: {item.title} ({item.conversation_id})"
            if command == "/conversations":
                items = self._manager.list(include_closed=argument == "--all")
                if not items:
                    return "No hay conversaciones."
                active = self._manager.active()
                lines = ["Conversaciones:"]
                for item in items:
                    marker = "*" if active and item.conversation_id == active.conversation_id else " "
                    lines.append(f"{marker} {item.title} [{item.status.value}] {item.conversation_id}")
                return "\n".join(lines)
            if command == "/use":
                item = self._manager.select(argument)
                self._request_factory.set_conversation_id(item.conversation_id)
                return f"Conversación activa: {item.title}"
            if command == "/rename":
                item = self._manager.rename_active(argument)
                return f"Conversación renombrada: {item.title}"
            if command == "/close":
                item = self._manager.close_active()
                active = self._manager.active()
                if active is None:
                    raise ContractError("no se pudo crear la conversación siguiente")
                self._request_factory.set_conversation_id(active.conversation_id)
                return f"Conversación cerrada: {item.title}. Se inició una nueva."
            if command == "/delete":
                parts = argument.rsplit(" ", 1)
                if len(parts) != 2 or parts[1] != "CONFIRM":
                    return "Uso: /delete <conversation_id> CONFIRM. Esta acción elimina permanentemente su historial."
                self._manager.delete(parts[0])
                active = self._manager.active()
                if active is None:
                    raise ContractError("no existe conversación activa tras eliminar")
                self._request_factory.set_conversation_id(active.conversation_id)
                return "Conversación eliminada permanentemente."
            if command == "/backup":
                if not argument:
                    return "Uso: /backup <ruta_absoluta>"
                password = getpass("Contraseña del respaldo (mínimo 12 caracteres): ")
                confirmation = getpass("Repite la contraseña: ")
                if password != confirmation:
                    return "Las contraseñas no coinciden; no se creó el respaldo."
                path = self._backup.create(argument, password)
                return f"Respaldo cifrado creado: {path}"
            if command == "/verify-backup":
                if not argument:
                    return "Uso: /verify-backup <ruta>"
                password = getpass("Contraseña del respaldo: ")
                self._backup.verify(argument, password)
                return "Respaldo auténtico e íntegro; esquema de conversaciones verificado."
        except (ContractError, NotFoundError) as exc:
            return f"No se pudo ejecutar el comando: {exc}"
        return None
