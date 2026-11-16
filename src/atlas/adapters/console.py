"""Adaptador de consola para la conversación local de Atlas."""

import sys
from typing import Callable, Protocol

from atlas.assistant.models import AssistantResponse, AssistantResponseKind


class AssistantRuntime(Protocol):
    def respond(self, content: str) -> AssistantResponse: ...
    def respond_streaming(self, content: str, on_token: Callable[[str], None]) -> AssistantResponse: ...


def _write_stdout(content: str) -> None:
    sys.stdout.write(content)
    sys.stdout.flush()


def _show_help(output_fn: Callable[[str], None]) -> None:
    output_fn(
        "Comandos de Atlas:\n"
        "  /help                 Muestra esta ayuda.\n"
        "  /clear                Limpia la pantalla.\n"
        "  /new [título]         Crea y selecciona una conversación.\n"
        "  /conversations [--all] Lista conversaciones.\n"
        "  /use <id>             Selecciona una conversación existente.\n"
        "  /rename <título>      Renombra la conversación activa.\n"
        "  /close                Cierra la activa y crea otra.\n"
        "  /exit                 Finaliza Atlas."
    )


def run_console(
    runtime: AssistantRuntime,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    write_fn: Callable[[str], None] = _write_stdout,
    command_handler: Callable[[str], str | None] | None = None,
) -> None:
    output_fn("Atlas está listo. Escribe '/help' para ver los comandos.")
    try:
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
            command = normalized.casefold()
            if command == "/help":
                _show_help(output_fn)
                continue
            if command == "/clear":
                write_fn("\033[2J\033[H")
                continue
            if command == "/exit" or command in {"salir", "exit", "quit"}:
                output_fn("Atlas: hasta luego.")
                return
            if command_handler is not None and normalized.startswith("/"):
                result = command_handler(normalized)
                if result is not None:
                    output_fn(result)
                    continue
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
                        write_fn("\nAtlas> " + response.content + "\n")
                    else:
                        write_fn(response.content + "\n")
                else:
                    write_fn("\n")
            else:
                response = runtime.respond(content)
                output_fn(f"Atlas> {response.content}")
    except KeyboardInterrupt:
        write_fn("\n")
        output_fn("Atlas: interrupción recibida. Sesión finalizada.")
