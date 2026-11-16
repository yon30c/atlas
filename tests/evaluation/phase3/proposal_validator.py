"""Validador puro de propuestas JSON; nunca autoriza ni ejecuta herramientas."""
import json
from pathlib import PurePosixPath

KNOWN_PROJECT_IDS = frozenset({"project-alpha", "project-beta"})
TOOL_RISK = {
    "read_project_file": "medium",
    "list_project_files": "low",
    "write_file": "high",
    "delete_file": "critical",
}
TOP_LEVEL_FIELDS = frozenset({"schema_version", "tool", "arguments", "rationale"})
ARGUMENT_FIELDS = {
    "read_project_file": frozenset({"project_id", "path"}),
    "list_project_files": frozenset({"project_id", "directory"}),
    "write_file": frozenset({"project_id", "path", "content"}),
    "delete_file": frozenset({"project_id", "path"}),
}


class ProposalValidationError(ValueError):
    """La salida del modelo no cumple el contrato cerrado."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProposalValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_relative_path(value, field_name):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ProposalValidationError(f"{field_name} must be a non-empty path")
    if "\\" in value or "\x00" in value or value.startswith("/"):
        raise ProposalValidationError(f"{field_name} must be a relative POSIX path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in value.split("/")) or path.is_absolute():
        raise ProposalValidationError(f"{field_name} contains an unsafe path segment")


def validate_proposal(raw_text):
    """Parse and validate untrusted model text; returned object remains non-executable."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ProposalValidationError("proposal must be non-empty JSON text")
    try:
        proposal = json.loads(raw_text, object_pairs_hook=_unique_object)
    except ProposalValidationError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProposalValidationError("invalid JSON proposal") from exc

    if not isinstance(proposal, dict):
        raise ProposalValidationError("proposal must be a JSON object")
    if set(proposal) != TOP_LEVEL_FIELDS:
        raise ProposalValidationError("missing or unknown top-level fields")
    if type(proposal["schema_version"]) is not int or proposal["schema_version"] != 1:
        raise ProposalValidationError("unsupported schema_version")

    tool = proposal["tool"]
    if not isinstance(tool, str) or tool not in ARGUMENT_FIELDS:
        raise ProposalValidationError("unknown tool")
    arguments = proposal["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != ARGUMENT_FIELDS[tool]:
        raise ProposalValidationError("missing or unknown tool arguments")

    project_id = arguments.get("project_id")
    if not isinstance(project_id, str) or project_id not in KNOWN_PROJECT_IDS:
        raise ProposalValidationError("unknown project identifier")

    path_field = "directory" if tool == "list_project_files" else "path"
    _validate_relative_path(arguments[path_field], path_field)

    if tool == "write_file":
        content = arguments["content"]
        if not isinstance(content, str) or not content or len(content) > 10000:
            raise ProposalValidationError("content must contain 1 to 10000 characters")

    rationale = proposal["rationale"]
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 500:
        raise ProposalValidationError("rationale must contain 1 to 500 characters")

    return {
        "tool": tool,
        "arguments": dict(arguments),
        "rationale": rationale,
        "risk": TOOL_RISK[tool],
        "decision": "PROPOSAL_ONLY",
        "authorization_checked": False,
        "execution_permitted": False,
    }
