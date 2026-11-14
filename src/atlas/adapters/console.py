"""Adaptador de consola para la conversación local de Atlas."""

import sys
from typing import Callable, Protocol

from atlas.assistant.models import AssistantResponse, AssistantResponseKind


class AssistantRuntime(Protocol):
    """Fachada de aplicación requerida por la interfaz de consola."""

    def respond(self, content: str) -> AssistantResponse:
        """Procesa el texto introducido y devuelve una respuesta."""

    def respond_streaming(
        self,
        content: str,
        on_token: Callable[[str], None],
    ) -> AssistantResponse:
        """Procesa el texto y emite fragmentos conforme llegan."""


def _write_stdout(content: str) -> None:
    sys.stdout.write(content)
    sys.stdout.flush()


def run_console(
    runtime: AssistantRuntime,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    write_fn: Callable[[str], None] = _write_stdout,
) -> None:
    """Ejecuta la conversación delegando la coordinación en AtlasCore."""
    output_fn("Atlas está listo. Escribe 'salir' para terminar.")

    while True:
        try:
            content = input_fn("Tú> ")
        except EOFError:
            output_fn("Atlas: sesión finalizada.")
            return
        if not isinstance(content, str):
            raise TypeError("input_fn debe devolver texto")

        normalized = content.strip()
        if not normalized:
            continue
        if normalized.casefold() in {"salir", "exit", "quit"}:
            output_fn("Atlas: hasta luego.")
            return

        streaming_responder = getattr(runtime, "respond_streaming", None)
        if callable(streaming_responder):
            write_fn("Atlas> ")
            streamed: list[str] = []

            def emit(token: str) -> None:
                if not isinstance(token, str):
                    raise TypeError("el streaming debe emitir fragmentos de texto")
                streamed.append(token)
                write_fn(token)

            response = streaming_responder(content, emit)
            if response.kind is AssistantResponseKind.ERROR:
                if streamed:
                    write_fn("\\nAtlas> " + response.content + "\\n")
                else:
                    write_fn(response.content + "\\n")
            else:
                write_fn("\\n")
        else:
            response = runtime.respond(content)
            output_fn(f"Atlas> {response.content}")
