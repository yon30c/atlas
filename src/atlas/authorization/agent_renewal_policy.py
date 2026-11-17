"""CAM contract for delegated AGENT Grant-renewal requests.

This module evaluates the explicit renewal action against the exact Grant
resources. It does not authenticate evidence; callers must revalidate both
AGENT and delegation evidence inside their shared authority UoW first.
"""
from datetime import datetime

from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    Grant,
)
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.agent_delegation import VerifiedAgentDelegationContext
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext


GRANT_RENEWAL_REQUEST_ACTION = "grant.renewal.request"


def require_agent_renewal_cam_allow(
    *,
    context: OperationContext,
    verified_agent_identity: VerifiedAgentIdentityContext,
    verified_delegation: VerifiedAgentDelegationContext,
    grant: Grant,
    evaluator: AuthorizationEvaluator,
    now: datetime,
) -> None:
    """Require exact delegation coverage and CAM ALLOW for every Grant resource.

    The function deliberately fails closed on partial resource coverage:
    the current renewal workflow extends the complete Grant, not a subset.
    Cryptographic/current-state verification is the caller's responsibility
    and must occur in the same UoW before this policy function is called.
    """
    if not isinstance(context, OperationContext):
        raise ContractError("context debe ser OperationContext")
    if not isinstance(verified_agent_identity, VerifiedAgentIdentityContext):
        raise AuthorizationError("se requiere evidencia AGENT verificada")
    if not isinstance(verified_delegation, VerifiedAgentDelegationContext):
        raise AuthorizationError("se requiere evidencia de delegación verificada")
    if not isinstance(grant, Grant):
        raise ContractError("grant debe ser Grant")
    if not isinstance(evaluator, AuthorizationEvaluator):
        raise ContractError("evaluator debe ser AuthorizationEvaluator")

    agent = verified_agent_identity
    delegation = verified_delegation
    if (
        context.actor.kind is not IdentityKind.AGENT
        or context.actor.status is not IdentityStatus.ACTIVE
        or context.delegation is not DelegationMode.DELEGATED
        or context.actor.identity_id != agent.identity_id
        or context.actor.revision != agent.identity_revision
        or context.user_id != delegation.owner_user_id
        or context.project_id != grant.project_id
        or context.environment != grant.environment
    ):
        raise AuthorizationError("el contexto de operación no coincide con AGENT y owner verificados")

    if (
        delegation.agent_identity_id != agent.identity_id
        or delegation.agent_identity_revision != agent.identity_revision
        or delegation.agent_context_id != agent.context_id
        or delegation.agent_binding_id != agent.binding_id
        or delegation.agent_binding_revision != agent.binding_revision
        or delegation.issuer_id != agent.issuer_id
        or delegation.owner_user_id != grant.owner_user_id
        or delegation.grant_id != grant.grant_id
        or delegation.grant_revision != grant.revision
        or delegation.project_id != grant.project_id
        or delegation.environment != grant.environment
    ):
        raise AuthorizationError("la evidencia de delegación no corresponde al Grant o AGENT")

    if (
        delegation.scope.resource_type != grant.resource_type
        or delegation.scope.resource_ids != grant.resource_ids
        or GRANT_RENEWAL_REQUEST_ACTION not in grant.actions
        or GRANT_RENEWAL_REQUEST_ACTION not in delegation.scope.actions
    ):
        raise AuthorizationError("la delegación no cubre exactamente la solicitud de renovación")

    for resource_id in sorted(grant.resource_ids):
        request = AuthorizationRequest(
            context=context,
            action=GRANT_RENEWAL_REQUEST_ACTION,
            resource_type=grant.resource_type,
            resource_id=resource_id,
            resource_owner_id=grant.owner_user_id,
        )
        evaluation = evaluator.evaluate(request, (grant,), now)
        if (
            evaluation.decision is not AuthorizationDecision.ALLOW
            or evaluation.matched_grant is None
            or evaluation.matched_grant.grant_id != grant.grant_id
            or evaluation.matched_grant.revision != grant.revision
        ):
            raise AuthorizationError("CAM denegó la solicitud de renovación del Grant")
