"""Autorización simulada con contexto confiable externo; nunca ejecuta herramientas."""
from dataclasses import dataclass

from .proposal_validator import TOOL_RISK


class AuthorizationContextError(ValueError):
    """El contexto confiable de autorización está ausente o mal formado."""


@dataclass(frozen=True)
class HumanApproval:
    project_id: str
    tool: str
    approval_id: str


@dataclass(frozen=True)
class AuthorizationContext:
    """Fixture de autoridad aportado fuera del texto generado por el modelo."""
    actor_id: str
    project_scopes: frozenset
    tool_permissions: frozenset
    human_approvals: tuple = ()


def authorize_proposal(proposal, context):
    """Decide si una propuesta puede avanzar en la simulación; jamás permite ejecución."""
    if not isinstance(context, AuthorizationContext):
        raise AuthorizationContextError("trusted AuthorizationContext is required")
    if not isinstance(context.actor_id, str) or not context.actor_id.strip():
        raise AuthorizationContextError("authenticated actor is required")
    if type(context.project_scopes) is not frozenset:
        raise AuthorizationContextError("project_scopes must be a trusted frozenset")
    if type(context.tool_permissions) is not frozenset:
        raise AuthorizationContextError("tool_permissions must be a trusted frozenset")
    if type(context.human_approvals) is not tuple:
        raise AuthorizationContextError("human_approvals must be a trusted tuple")
    if not isinstance(proposal, dict) or set(proposal) != {
        "tool", "arguments", "rationale", "risk", "decision",
        "authorization_checked", "execution_permitted"
    }:
        raise AuthorizationContextError("validated proposal object required")

    tool = proposal["tool"]
    arguments = proposal["arguments"]
    project_id = arguments.get("project_id") if isinstance(arguments, dict) else None
    risk = TOOL_RISK.get(tool)
    if risk is None or proposal["risk"] != risk:
        raise AuthorizationContextError("proposal risk/tool mismatch")

    reasons = []
    if project_id not in context.project_scopes:
        reasons.append("PROJECT_SCOPE_MISSING")
    if tool not in context.tool_permissions:
        reasons.append("TOOL_PERMISSION_MISSING")

    approval_required = risk in {"high", "critical"}
    matching_approvals = [
        grant for grant in context.human_approvals
        if isinstance(grant, HumanApproval)
        and grant.project_id == project_id
        and grant.tool == tool
        and isinstance(grant.approval_id, str)
        and grant.approval_id.strip()
    ]
    if approval_required and not matching_approvals:
        reasons.append("HUMAN_APPROVAL_MISSING")

    authorized = not reasons
    return {
        "actor_id": context.actor_id,
        "tool": tool,
        "project_id": project_id,
        "decision": "AUTHORIZED_FOR_SIMULATION" if authorized else "DENIED",
        "reasons": reasons,
        "authorization_checked": True,
        "execution_permitted": False,
        "approval_required": approval_required,
        "approval_id": matching_approvals[0].approval_id if approval_required and matching_approvals else None,
    }
