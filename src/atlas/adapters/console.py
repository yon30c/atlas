"""Adaptador de consola para la conversación local de Atlas."""

from typing import Callable, Protocol

from atlas.assistant.models import AssistantRequest, AssistantResponse


class AssistantResponder(Protocol):
    """Contrato mínimo requerido por la interfaz de consola."""

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Procesa una solicitud y devuelve su respuesta."""


class AssistantRequestFactory(Protocol):
    """Construye solicitudes con el contexto local correspondiente."""

    def create(self, content: str) -> AssistantRequest:
        """Crea una solicitud a partir del texto introducido."""


def run_console(
    responder: AssistantResponder,
    request_factory: AssistantRequestFactory,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Ejecuta el bucle de conversación sin decidir cómo se construye el contexto.

    La composición concreta del perfil local, el reloj y el generador de
    respuestas queda fuera de este adaptador.
    """
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
        response = responder.respond(request)
        output_fn(f"Atlas> {response.content}")
