"""Exportación explícita y portable de conversaciones locales."""

import json
import os
from pathlib import Path
import stat

from atlas.core.errors import ContractError, NotFoundError


class ConversationExport:
    """Exporta metadatos e historial completo a JSON sin modificar la base activa.

    El JSON es texto legible y no está cifrado. El archivo se crea con modo
    0600, sin seguir enlaces simbólicos ni sobrescribir destinos existentes.
    """

    def __init__(self, repository) -> None:
        if not callable(getattr(repository, "get", None)) or not callable(
            getattr(repository, "get_history", None)
        ):
            raise ContractError("repository debe permitir leer conversaciones e historial")
        self._repository = repository

    def export(self, conversation_id: str, destination: str | Path) -> Path:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ContractError("conversation_id debe ser una cadena no vacía")

        target = Path(destination).expanduser()
        if not target.is_absolute() or not target.parent.is_dir():
            raise ContractError("el destino debe ser absoluto y su directorio debe existir")

        conversation = self._repository.get(conversation_id.strip())
        if conversation is None:
            raise NotFoundError("conversación no encontrada")

        messages = self._repository.get_history(conversation.conversation_id)
        payload = {
            "format": "atlas-conversation-export",
            "format_version": 1,
            "conversation": {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "status": conversation.status.value,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
                "last_message_at": (
                    None if conversation.last_message_at is None
                    else conversation.last_message_at.isoformat()
                ),
            },
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
        }
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o600)
        except FileExistsError as exc:
            raise ContractError("el archivo de exportación ya existe; no se sobrescribirá") from exc
        except OSError as exc:
            raise ContractError("no se pudo crear el archivo de exportación") from exc

        try:
            os.fchmod(fd, 0o600)
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("escritura incompleta")
                view = view[written:]
            os.fsync(fd)
        except Exception as exc:
            try:
                os.unlink(target)
            except OSError:
                pass
            if isinstance(exc, OSError):
                raise ContractError("no se pudo completar la exportación") from exc
            raise
        finally:
            os.close(fd)

        try:
            directory_fd = os.open(
                target.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # El archivo ya está completo y sincronizado; la sincronización del
            # directorio no está soportada por todos los sistemas de archivos.
            pass
        return target
