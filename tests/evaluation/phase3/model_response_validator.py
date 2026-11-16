"""Validador del sobre de respuesta del modelo; nunca autoriza ni ejecuta."""
import json

from .proposal_validator import (
    ProposalValidationError,
    _unique_object,
    validate_proposal,
)


class ModelResponseValidationError(ValueError):
    """La respuesta del modelo no cumple el contrato de propuesta o negativa."""


def validate_model_response(raw_text):
    """Validate a closed response envelope and preserve proposal-only semantics."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ModelResponseValidationError("response must be non-empty JSON text")
    try:
        response = json.loads(raw_text, object_pairs_hook=_unique_object)
    except (ProposalValidationError, json.JSONDecodeError, TypeError) as exc:
        raise ModelResponseValidationError("invalid model response JSON") from exc

    if not isinstance(response, dict):
        raise ModelResponseValidationError("response must be a JSON object")
    if type(response.get("schema_version")) is not int or response["schema_version"] != 1:
        raise ModelResponseValidationError("unsupported schema_version")

    status = response.get("status")
    if status == "refusal":
        if set(response) != {"schema_version", "status", "reason"}:
            raise ModelResponseValidationError("refusal contains missing or unknown fields")
        reason = response["reason"]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ModelResponseValidationError("refusal reason must contain 1 to 500 characters")
        return {
            "status": "REFUSAL",
            "reason": reason,
            "proposal": None,
            "execution_permitted": False,
        }

    if status == "proposal":
        if set(response) != {"schema_version", "status", "proposal"}:
            raise ModelResponseValidationError("proposal response contains missing or unknown fields")
        try:
            proposal = validate_proposal(json.dumps(response["proposal"], ensure_ascii=False))
        except (ProposalValidationError, TypeError) as exc:
            raise ModelResponseValidationError("embedded proposal is invalid") from exc
        return {
            "status": "PROPOSAL",
            "reason": None,
            "proposal": proposal,
            "execution_permitted": False,
        }

    raise ModelResponseValidationError("status must be proposal or refusal")
