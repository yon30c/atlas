"""Punto de composición para ejecutar Atlas en una terminal local."""

import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from atlas.adapters.console import run_console
from atlas.adapters.console_conversations import ConversationConsoleCommands
from atlas.adapters.ollama import OllamaProvider
from atlas.adapters.ollama_assistant import OllamaResponseGenerator
from atlas.adapters.sqlite import SQLiteConversationRepository, SQLiteDatabase
from atlas.adapters.sqlite.conversation_backup import ConversationBackup
from atlas.adapters.sqlite.conversation_export import ConversationExport
from atlas.adapters.sqlite.conversation_storage import prepare_conversation_database_path
from atlas.adapters.system_clock import SystemClock
from atlas.application import AtlasCore, ConversationContextProcessor
from atlas.application.conversation_manager import ConversationManager
from atlas.assistant.conversation import Conversation, ConversationStatus
from atlas.assistant.local_console import LocalConsoleRequestFactory, LocalModeResponseGenerator
from atlas.assistant.service import AssistantService
from atlas.ports.llm import LLMProvider


DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_CONVERSATION_HISTORY_TURNS = 8
DEFAULT_CONVERSATION_MESSAGE_CHARS = 2000


def main(
    *, input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    write_fn: Callable[[str], None] | None = None,
    user_id: str | None = None, provider: LLMProvider | None = None,
    model: str | None = None, ollama_url: str | None = None,
    conversation_db_path: str | Path | None = None,
) -> None:
    """Inicia Atlas con historial SQLite privado, gestión y backup cifrado.

    ATLAS_CONVERSATION_DB permite seleccionar una base restaurada o alternativa.
    """
    clock = SystemClock()
    selected_db_path = conversation_db_path
    if selected_db_path is None:
        selected_db_path = os.environ.get("ATLAS_CONVERSATION_DB")
    database_path = prepare_conversation_database_path(selected_db_path)
    database = SQLiteDatabase(database_path)
    repository = SQLiteConversationRepository(database)
    repository.initialize()
    os.chmod(database_path, 0o600)
    active = repository.get_active_conversation()
    if active is None:
        now = clock.now()
        active = Conversation(
            conversation_id=str(uuid4()), title="Nueva conversación",
            status=ConversationStatus.ACTIVE, created_at=now, updated_at=now,
        )
        repository.create(active)
        repository.set_active_conversation(active.conversation_id)

    request_factory = LocalConsoleRequestFactory(clock, user_id=user_id, conversation_id=active.conversation_id)
    manager = ConversationManager(repository, clock)
    backup = ConversationBackup(database)
    export = ConversationExport(repository)
    handler = ConversationConsoleCommands(manager, request_factory, backup, export)

    if os.environ.get("ATLAS_MODE", "").strip().casefold() == "offline":
        generator = LocalModeResponseGenerator()
    else:
        selected_model = model if model is not None else (os.environ.get("ATLAS_MODEL") or DEFAULT_MODEL)
        selected_url = ollama_url if ollama_url is not None else os.environ.get("ATLAS_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        selected_provider = provider if provider is not None else OllamaProvider(base_url=selected_url)
        generator = OllamaResponseGenerator(provider=selected_provider, model=selected_model)

    service = AssistantService(response_generator=generator, clock=clock)
    processor = ConversationContextProcessor(
        assistant=service, history_store=repository,
        max_history_turns=DEFAULT_CONVERSATION_HISTORY_TURNS,
        max_message_chars=DEFAULT_CONVERSATION_MESSAGE_CHARS,
    )
    core = AtlasCore(request_factory=request_factory, assistant=processor)
    options = {"input_fn": input_fn, "output_fn": output_fn, "command_handler": handler.handle}
    if write_fn is not None:
        options["write_fn"] = write_fn
    run_console(core, **options)
