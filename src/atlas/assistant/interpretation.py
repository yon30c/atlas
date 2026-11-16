"""Parser estricto para salidas estructuradas de interpretación de intención."""

import json
from typing import object as _object  # type: ignore[attr-defined]

from atlas.assistant.planning import (
    AssistantIntent,
    IntentInterpretation,
    IntentKind,
    InterpretationStatus,
)
from atlas.core.errors import ContractError


def parse_intent_interpretation(content: str) -> IntentInterpretation:
    """Convierte JSON no confiable en un contrato tipado y cerrado.

    El contenido del modelo solo puede proponer una intención conocida.
    Este parser no autoriza ni ejecuta capacidades.
    """
    if not isinstance(content, str) or not content.strip():
        raise ContractError("la salida estructurada debe ser texto no vacío")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ContractError("la salida del intérprete no es JSON válido") from exc
    if not isinstance(payload, dict):
        raise ContractError("la salida del intérprete debe ser un objeto JSON")

    allowed_keys = {"status", "kind", "parameters", "message"}
    if set(payload) != allowed_keys:
        raise ContractError("la salida contiene campos ausentes o desconocidos")

    try:
        status = InterpretationStatus(payload["status"])
    except (TypeError, ValueError) as exc:
        raise ContractError("status no es un valor de interpretación admitido") from exc

    kind_value = payload["kind"]
    parameters_value = payload["parameters"]
    message_value = payload["message"]

    if status is InterpretationStatus.READY:
        if not isinstance(kind_value, str):
            raise ContractError("READY requiere un kind válido")
        try:
            kind = IntentKind(kind_value)
        except ValueError as exc:
            raise ContractError("kind no corresponde a una capacidad admitida") from exc
        if not isinstance(parameters_value, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in parameters_value.items()
        ):
            raise ContractError("parameters debe ser un objeto de cadenas")
        if message_value is not None:
            raise ContractError("READY no admite message")
        intent = AssistantIntent(kind, tuple(parameters_value.items()))
        return IntentInterpretation(InterpretationStatus.READY, intent=intent)

    if kind_value is not None:
        raise ContractError("una interpretación sin READY no puede incluir kind")
    if parameters_value != {}:
        raise ContractError("una interpretación sin READY no puede incluir parameters")
    if not isinstance(message_value, str) or not message_value.strip():
        raise ContractError("la aclaración o rechazo requiere message")
    return IntentInterpretation(status, message=message_value.strip())
