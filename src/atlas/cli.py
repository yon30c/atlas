"""Punto de composición para ejecutar Atlas en una terminal local."""

import os
from typing import Callable

from atlas.adapters.console import run_console
from atlas.adapters.ollama import OllamaProvider
from atlas.adapters.ollama_assistant import OllamaResponseGenerator
from atlas.adapters.system_clock import SystemClock
from atlas.application import (
    AtlasCore,
    ConversationContextProcessor,
    InMemoryConversationHistory,
)
from atlas.assistant.local_console import (
    LocalConsoleRequestFactory,
    LocalModeResponseGenerator,
)
from atlas.assistant.service import AssistantService
from atlas.ports.llm import LLMProvider


DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_CONVERSATION_HISTORY_TURNS = 8
DEFAULT_CONVERSATION_MESSAGE_CHARS = 2000


def main(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    write_fn: Callable[[str], None] | None = None,
    user_id: str | None = None,
    provider: LLMProvider | None = None,
    model: str | None = None,
    ollama_url: str | None = None,
) -> None:
    """Inicia Atlas con Gemma local, streaming e historial de sesión acotado.

    ATLAS_MODEL y ATLAS_OLLAMA_URL permiten cambiar el modelo o el endpoint.
    El adaptador rechaza cualquier endpoint que no sea loopback.
    ATLAS_MODE=offline conserva el modo informativo sin proveedor LLM.
    El historial en memoria conserva hasta ocho turnos, con 2000 caracteres
    como máximo por mensaje histórico.
    """
    clock = SystemClock()
    request_factory = LocalConsoleRequestFactory(clock, user_id=user_id)

    if os.environ.get("ATLAS_MODE", "").strip().casefold() == "offline":
        response_generator = LocalModeResponseGenerator()
    else:
        selected_model = (
            model
            if model is not None
            else (os.environ.get("ATLAS_MODEL") or DEFAULT_MODEL)
        )
        selected_url = (
            ollama_url
            if ollama_url is not None
            else os.environ.get("ATLAS_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        )
        selected_provider = (
            provider if provider is not None else OllamaProvider(base_url=selected_url)
        )
        response_generator = OllamaResponseGenerator(
            provider=selected_provider,
            model=selected_model,
        )

    assistant_service = AssistantService(
        response_generator=response_generator,
        clock=clock,
    )
    conversation_processor = ConversationContextProcessor(
        assistant=assistant_service,
        history_store=InMemoryConversationHistory(
            max_turns=DEFAULT_CONVERSATION_HISTORY_TURNS,
            max_message_chars=DEFAULT_CONVERSATION_MESSAGE_CHARS,
        ),
    )
    atlas_core = AtlasCore(
        request_factory=request_factory,
        assistant=conversation_processor,
    )
    console_options = {
        "input_fn": input_fn,
        "output_fn": output_fn,
    }
    if write_fn is not None:
        console_options["write_fn"] = write_fn
    run_console(atlas_core, **console_options)
