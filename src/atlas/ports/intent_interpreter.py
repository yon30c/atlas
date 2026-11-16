"""Puerto de aplicación para interpretar solicitudes del usuario."""

from typing import Protocol

from atlas.assistant.planning import IntentInterpretation


class IntentInterpreter(Protocol):
    """Interpreta lenguaje natural sin ejecutar capacidades."""

    def interpret(self, content: str) -> IntentInterpretation:
        """Devuelve una intención validada, una aclaración o un rechazo."""
