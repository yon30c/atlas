"""Trusted issuance and revalidation of short-lived AGENT delegation evidence.

This service proves that an authenticated canonical AGENT is currently covered
by one owner-issued delegation and its exact live CAM Grant revision. It is not
a CAM policy evaluator and never authorizes an operation by itself.
"""

from dataclasses import replace
from datetime import datetime, timedelta
import re
import secrets
from typing import Protocol
from uuid import uuid4

from atlas.authorization.models import Grant
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationStatus,
    VerifiedAgentDelegationContext,
)
from atlas.core.errors import AuthorizationError, ContractError, NotFoundError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext
from atlas.identity.verified_agent_identity_context_service import (
    VerifiedAgentIdentityContextRejected,
)
from atlas.ports.clock import Clock
from atlas.ports.verified_agent_delegation_context_verifier import VerifiedAgentDelegationContextVerifierPort


_REALM_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}", re.ASCII)
_AUDIENCE_RE = re.compile(r"[a-z][a-z0-9._:-]{0,127}", re.ASCII)


class VerifiedAgentDelegationContextRejected(AuthorizationError):
    """Delegation evidence is invalid, expired, revoked, or no longer current."""


class VerifiedAgentDelegationContextUnavailable(AuthorizationError):
    """A trusted delegation dependency is unavailable."""


class _AgentVerifier(Protocol):
    def verify_in_unit_of_work(self, context: VerifiedAgentIdentityContext, unit): ...


class VerifiedAgentDelegationContextService(VerifiedAgentDelegationContextVerifierPort):
    """Issues and revalidates AGENT delegation evidence using trusted config.

    Realm, audience, clock, TTL and attestor are injected by the composition
    root. Callers cannot select or weaken any of those security parameters.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory,
        agent_context_verifier: _AgentVerifier,
        clock: Clock,
        attestor,
        realm: str,
        audience: str,
        context_ttl: timedelta,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(agent_context_verifier, "verify_in_unit_of_work", None)):
            raise ContractError("agent_context_verifier no admite verificación en UoW")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")
        if not callable(getattr(attestor, "sign", None)) or not callable(getattr(attestor, "verify", None)):
            raise ContractError("attestor no implementa sign/verify")
        if not isinstance(realm, str) or _REALM_RE.fullmatch(realm) is None:
            raise ContractError("realm confiable debe ser lowercase ASCII canónico")
        if not isinstance(audience, str) or _AUDIENCE_RE.fullmatch(audience) is None:
            raise ContractError("audience confiable debe ser un identificador interno ASCII")
        if not isinstance(context_ttl, timedelta) or not (timedelta(0) < context_ttl <= timedelta(minutes=1)):
            raise ContractError("context_ttl debe estar entre 0 y 1 minuto")
        self._uow_factory = unit_of_work_factory
        self._agent_verifier = agent_context_verifier
        self._clock = clock
        self._attestor = attestor
        self._realm = realm
        self._audience = audience
        self._context_ttl = context_ttl

    def _now(self) -> datetime:
        value = self._clock.now()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise VerifiedAgentDelegationContextUnavailable("reloj UTC no disponible")
        return value

    def _payload(self, context: VerifiedAgentDelegationContext) -> bytes:
        return (
            b"atlas.verified-agent-delegation-context.v1\\x00"
            + self._realm.encode("ascii") + b"\\x00"
            + self._audience.encode("ascii") + b"\\x00"
            + context.attestation_payload()
        )

    @staticmethod
    def _require_live_bindings(unit, delegation: AgentDelegation, grant: Grant, now: datetime) -> None:
        if delegation.status is not AgentDelegationStatus.ACTIVE:
            raise VerifiedAgentDelegationContextRejected("delegación no activa")
        if not (delegation.not_before <= now < delegation.expires_at):
            raise VerifiedAgentDelegationContextRejected("delegación fuera de su ventana de validez")
        if (
            grant.grant_id != delegation.grant_id
            or grant.revision != delegation.grant_revision
            or grant.owner_user_id != delegation.owner_user_id
            or grant.subject_identity_id != delegation.agent_identity_id
            or grant.project_id != delegation.project_id
            or grant.environment != delegation.environment
            or grant.resource_type != delegation.scope.resource_type
            or grant.revoked_at is not None
            or grant.issued_at > now
            or grant.expires_at <= now
            or not delegation.scope.resource_ids.issubset(grant.resource_ids)
            or not delegation.scope.actions.issubset(grant.actions)
            or delegation.expires_at > grant.expires_at
        ):
            raise VerifiedAgentDelegationContextRejected("el Grant ya no coincide con la delegación")

        owner = unit.identity.get_user_by_identity_id(delegation.owner_identity_id)
        if (
            owner is None
            or owner.user_id != delegation.owner_user_id
            or owner.identity.kind is not IdentityKind.USER
            or owner.identity.status is not IdentityStatus.ACTIVE
        ):
            raise VerifiedAgentDelegationContextRejected("el propietario canónico no está activo")

        agent = unit.agent_identity.get_agent_by_identity_id(delegation.agent_identity_id)
        if (
            agent is None
            or agent.identity.identity_id != delegation.agent_identity_id
            or agent.identity.kind is not IdentityKind.AGENT
            or agent.identity.status is not IdentityStatus.ACTIVE
            or not unit.native_agent_identity.has_active_native_agent_binding(
                delegation.agent_identity_id, delegation.issuer_id
            )
        ):
            raise VerifiedAgentDelegationContextRejected("la identidad o vinculación AGENT no está activa")


    def verify_for_operation(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        verified_agent_identity: VerifiedAgentIdentityContext,
    ) -> VerifiedAgentDelegationContext:
        """Authenticate the AGENT and mint evidence from current canonical state."""
        from atlas.core.user_identity import validate_canonical_uuid4

        validate_canonical_uuid4(delegation_id, "delegation_id")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ContractError("expected_revision debe ser entero positivo")
        if not isinstance(verified_agent_identity, VerifiedAgentIdentityContext):
            raise VerifiedAgentDelegationContextRejected("se requiere evidencia AGENT verificada")

        try:
            with self._uow_factory() as unit:
                now = self._now()
                canonical_agent = self._agent_verifier.verify_in_unit_of_work(verified_agent_identity, unit)
                if canonical_agent.identity.identity_id != verified_agent_identity.identity_id:
                    raise VerifiedAgentDelegationContextRejected("identidad AGENT no coincide")
                delegation = unit.agent_delegations.get(delegation_id)
                if delegation is None:
                    raise NotFoundError("delegación no encontrada")
                if delegation.revision != expected_revision:
                    raise VerifiedAgentDelegationContextRejected("revisión de delegación obsoleta")
                if (
                    delegation.agent_identity_id != canonical_agent.identity.identity_id
                    or delegation.issuer_id != verified_agent_identity.issuer_id
                ):
                    raise VerifiedAgentDelegationContextRejected("el AGENT autenticado no es el destinatario o issuer delegado")
                grant = unit.grants.get(delegation.grant_id)
                if grant is None:
                    raise VerifiedAgentDelegationContextRejected("Grant canónico no encontrado")
                self._require_live_bindings(unit, delegation, grant, now)

                provisional = VerifiedAgentDelegationContext(
                    context_id=str(uuid4()),
                    delegation_id=delegation.delegation_id,
                    delegation_revision=delegation.revision,
                    owner_user_id=delegation.owner_user_id,
                    owner_identity_id=delegation.owner_identity_id,
                    agent_identity_id=delegation.agent_identity_id,
                    agent_identity_revision=canonical_agent.identity.revision,
                    agent_context_id=verified_agent_identity.context_id,
                    agent_binding_id=verified_agent_identity.binding_id,
                    agent_binding_revision=verified_agent_identity.binding_revision,
                    grant_id=delegation.grant_id,
                    grant_revision=delegation.grant_revision,
                    project_id=delegation.project_id,
                    environment=delegation.environment,
                    scope=delegation.scope,
                    issuer_id=delegation.issuer_id,
                    realm=self._realm,
                    audience=self._audience,
                    verified_at=now,
                    expires_at=min(now + self._context_ttl, delegation.expires_at, grant.expires_at),
                    verification_ref=secrets.token_urlsafe(32),
                    attestation=secrets.token_urlsafe(32),
                )
                context = replace(provisional, attestation=self._attestor.sign(self._payload(provisional)))
                unit.commit()
                return context
        except (VerifiedAgentDelegationContextRejected, VerifiedAgentIdentityContextRejected, ContractError, NotFoundError):
            raise
        except Exception as exc:
            raise VerifiedAgentDelegationContextUnavailable("no se pudo verificar la delegación AGENT") from exc

    def verify(self, context: VerifiedAgentDelegationContext) -> AgentDelegation:
        """Revalidate signed delegation evidence and all canonical bindings."""
        try:
            with self._uow_factory() as unit:
                return self.verify_in_unit_of_work(context, unit)
        except (VerifiedAgentDelegationContextRejected, ContractError, NotFoundError):
            raise
        except Exception as exc:
            raise VerifiedAgentDelegationContextUnavailable("no se pudo revalidar la delegación AGENT") from exc

    def verify_in_unit_of_work(self, context: VerifiedAgentDelegationContext, unit) -> AgentDelegation:
        """Revalidate evidence inside a caller-owned transaction; never commits it."""
        if not isinstance(context, VerifiedAgentDelegationContext):
            raise VerifiedAgentDelegationContextRejected("contexto de delegación no válido")
        now = self._now()
        if (
            context.realm != self._realm
            or context.audience != self._audience
            or context.expires_at <= now
            or context.verified_at > now
            or context.expires_at - context.verified_at > self._context_ttl
            or not self._attestor.verify(self._payload(context), context.attestation)
        ):
            raise VerifiedAgentDelegationContextRejected("contexto de delegación no válido")
        delegation = unit.agent_delegations.get(context.delegation_id)
        if delegation is None:
            raise VerifiedAgentDelegationContextRejected("delegación no encontrada")
        if (
            delegation.revision != context.delegation_revision
            or delegation.owner_user_id != context.owner_user_id
            or delegation.owner_identity_id != context.owner_identity_id
            or delegation.agent_identity_id != context.agent_identity_id
            or delegation.grant_id != context.grant_id
            or delegation.grant_revision != context.grant_revision
            or delegation.project_id != context.project_id
            or delegation.environment != context.environment
            or delegation.scope != context.scope
            or delegation.issuer_id != context.issuer_id
        ):
            raise VerifiedAgentDelegationContextRejected("los claims de delegación cambiaron")
        grant = unit.grants.get(delegation.grant_id)
        if grant is None:
            raise VerifiedAgentDelegationContextRejected("Grant canónico no encontrado")
        self._require_live_bindings(unit, delegation, grant, now)
        agent = unit.agent_identity.get_agent_by_identity_id(context.agent_identity_id)
        binding = unit.native_agent_identity.get_native_agent_binding_by_id(context.agent_binding_id)
        if (
            agent is None
            or agent.identity.revision != context.agent_identity_revision
            or binding is None
            or binding.identity_id != context.agent_identity_id
            or binding.issuer_id != context.issuer_id
            or binding.revision != context.agent_binding_revision
            or binding.status.value != "active"
        ):
            raise VerifiedAgentDelegationContextRejected("la identidad o binding AGENT cambió")
        return delegation
