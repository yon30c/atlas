"""Punto de composición para ejecutar Atlas en una terminal local."""

from typing import Callable

from atlas.adapters.console import run_console
from atlas.adapters.system_clock import SystemClock
from atlas.assistant.local_console import (
    LocalConsoleRequestFactory,
    LocalModeResponseGenerator,
)
from atlas.assistant.service import AssistantService


def main(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    user_id: str | None = None,
) -> None:
    """Construye las dependencias locales e inicia la conversación."""
    clock = SystemClock()
    request_factory = LocalConsoleRequestFactory(clock, user_id=user_id)
    assistant = AssistantService(
        response_generator=LocalModeResponseGenerator(),
        clock=clock,
    )
    run_console(
        assistant,
        request_factory,
        input_fn=input_fn,
        output_fn=output_fn,
    )
