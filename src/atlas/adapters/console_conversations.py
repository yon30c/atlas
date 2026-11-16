"""Comandos de consola para administrar conversaciones locales."""

from getpass import getpass
import shlex

from atlas.adapters.sqlite.conversation_backup import ConversationBackup
from atlas.adapters.sqlite.conversation_export import ConversationExport
from atlas.application.conversation_manager import ConversationManager
from atlas.assistant.local_console import LocalConsoleRequestFactory
from atlas.core.errors import ContractError, NotFoundError


class ConversationConsoleCommands:
    def __init__(self, manager: ConversationManager, request_factory: LocalConsoleRequestFactory, backup: ConversationBackup, export: ConversationExport) -> None:
        self._manager = manager
        self._request_factory = request_factory
        self._backup = backup
        self._export = export

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
                    return "Uso: /delete <conversation_id> CONFIRM. Elimina permanentemente el historial."
                self._manager.delete(parts[0])
                active = self._manager.active()
                if active is None:
                    raise ContractError("no existe conversación activa tras eliminar")
                self._request_factory.set_conversation_id(active.conversation_id)
                return "Conversación eliminada permanentemente."
            if command == "/export":
                args = shlex.split(argument)
                if len(args) == 1:
                    active = self._manager.active()
                    if active is None:
                        raise ContractError("no hay una conversación activa")
                    conversation_id, destination = active.conversation_id, args[0]
                elif len(args) == 2:
                    conversation_id, destination = args
                else:
                    return 'Uso: /export ["conversation_id"] "<ruta_absoluta.json>"'
                path = self._export.export(conversation_id, destination)
                return f"Conversación exportada a JSON: {path} (sin cifrar; protege el archivo)."
            if command == "/backup":
                args = shlex.split(argument)
                if len(args) != 1:
                    return 'Uso: /backup "<ruta_absoluta>"'
                password = getpass("Contraseña del respaldo (mínimo 12 caracteres): ")
                confirmation = getpass("Repite la contraseña: ")
                if password != confirmation:
                    return "Las contraseñas no coinciden; no se creó el respaldo."
                path = self._backup.create(args[0], password)
                return f"Respaldo cifrado creado: {path}"
            if command == "/verify-backup":
                args = shlex.split(argument)
                if len(args) != 1:
                    return 'Uso: /verify-backup "<ruta>"'
                password = getpass("Contraseña del respaldo: ")
                self._backup.verify(args[0], password)
                return "Respaldo auténtico e íntegro; esquema de conversaciones verificado."
            if command == "/restore-backup":
                args = shlex.split(argument)
                if len(args) != 2:
                    return 'Uso: /restore-backup "<respaldo>" "<nueva-ruta-db>"'
                password = getpass("Contraseña del respaldo: ")
                restored = self._backup.restore_to(args[0], password, args[1])
                return (
                    f"Base restaurada y verificada en {restored}. "
                    f"Sal de Atlas y reinicia con ATLAS_CONVERSATION_DB={restored} atlas."
                )
        except (ContractError, NotFoundError, ValueError) as exc:
            return f"No se pudo ejecutar el comando: {exc}"
        return None
