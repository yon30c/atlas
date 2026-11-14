"""Adaptador de consola para la conversación local de Atlas."""

import sys
from typing import Callable, Protocol

from atlas.assistant.models import AssistantRequest, AssistantResponse, AssistantResponseKind


class AssistantResponder(Protocol):
    """Contrato mínimo requerido por la interfaz de consola."""

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Procesa una solicitud y devuelve su respuesta."""


class AssistantRequestFactory(Protocol):
    """Construye solicitudes con el contexto local correspondiente."""

    def create(self, content: str) -> AssistantRequest:
        """Crea una solicitud a partir del texto introducido."""


def _write_stdout(content: str) -> None:
    sys.stdout.write(content)
    sys.stdout.flush()


def run_console(
    responder: AssistantResponder,
    request_factory: AssistantRequestFactory,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    write_fn: Callable[[str], None] = _write_stdout,
) -> None:
    """Ejecuta la conversación y muestra tokens conforme se reciben."""
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

        request = request_factory.create(content)
        streaming_responder = getattr(responder, "respond_streaming", None)
        if callable(streaming_responder):
            write_fn("Atlas> ")
            streamed: list[str] = []

            def emit(token: str) -> None:
                if not isinstance(token, str):
                    raise TypeError("el streaming debe emitir fragmentos de texto")
                streamed.append(token)
                write_fn(token)

            response = streaming_responder(request, emit)
            if response.kind is AssistantResponseKind.ERROR:
                if streamed:
                    write_fn("\nAtlas> " + response.content + "\n")
                else:
                    write_fn(response.content + "\n")
            else:
                write_fn("\n")
        else:
            response = responder.respond(request)
            output_fn(f"Atlas> {response.content}")
