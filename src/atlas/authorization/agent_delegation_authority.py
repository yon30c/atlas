"""Owner-consented AGENT delegation lifecycle over one local authority UoW."""

from datetime import datetime, timedelta
from typing import Protocol
from uuid import uuid4

from atlas.authorization.models import Grant
from atlas.core.agent_delegation import AgentDelegation, AgentDelegationScope
from atlas.core.errors import AuthorizationError, ContractError, NotFoundError
from atlas.core.identity import IdentityStatus
from atlas.core.user_identity import validate_canonical_uuid4
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.ports.clock import Clock


def _require_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser datetime UTC")


class _OwnerContextVerifier(Protocol):
    def verify_in_unit_of_work(self, context: VerifiedIdentityContext, unit): ...


class SQLiteAgentDelegationAuthority:
    """Issues and revokes delegations after same-transaction owner verification.

    Delegated operation evidence is issued only through an explicitly
    configured verifier; absence of that dependency is fail-closed. This class
    is not a CAM engine. Revocation timestamps use the trusted clock.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory,
        owner_context_verifier: _OwnerContextVerifier,
        clock: Clock,
        operation_verifier=None,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(owner_context_verifier, "verify_in_unit_of_work", None)):
            raise ContractError("owner_context_verifier no admite verificación en UoW")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")
        self._uow_factory = unit_of_work_factory
        self._owner_verifier = owner_context_verifier
        if operation_verifier is not None and not callable(getattr(operation_verifier, "verify_for_operation", None)):
            raise ContractError("operation_verifier no implementa verify_for_operation")
        self._clock = clock
        self._operation_verifier = operation_verifier

    def verify_for_operation(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        verified_agent_identity,
    ):
        """Delegate operation evidence issuance to the separately configured verifier."""
        if self._operation_verifier is None:
            raise AuthorizationError("la verificación de delegaciones AGENT no está configurada")
        return self._operation_verifier.verify_for_operation(
            delegation_id,
            expected_revision=expected_revision,
            verified_agent_identity=verified_agent_identity,
        )

    def create_for_grant(
        self, *, grant_id: str, agent_identity_id: str,
        scope: AgentDelegationScope, not_before: datetime, expires_at: datetime,
        verified_owner_identity: VerifiedIdentityContext,
    ) -> AgentDelegation:
        """Issue owner consent bound to the exact active Grant and AGENT."""
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ContractError("grant_id debe ser una cadena no vacía")
        validate_canonical_uuid4(agent_identity_id, "agent_identity_id")
        if not isinstance(scope, AgentDelegationScope):
            raise ContractError("scope debe ser AgentDelegationScope")
        _require_utc(not_before, "not_before")
        _require_utc(expires_at, "expires_at")
        if not isinstance(verified_owner_identity, VerifiedIdentityContext):
            raise AuthorizationError("se requiere evidencia USER verificada")

        if expires_at <= not_before:
            raise ContractError("expires_at debe ser posterior a not_before")

        try:
            with self._uow_factory() as unit:
                # Read time only after BEGIN IMMEDIATE has acquired the write
                # transaction, so waiting for the lock cannot stale the window.
                now = self._clock.now()
                _require_utc(now, "clock.now()")
                if not_before < now or expires_at <= now:
                    raise ContractError("la ventana de delegación debe estar vigente al emitir")
                owner = self._owner_verifier.verify_in_unit_of_work(
                    verified_owner_identity, unit
                )
                if (
                    owner.user_id != verified_owner_identity.user_id
                    or owner.identity.identity_id != verified_owner_identity.identity_id
                    or owner.identity.status is not IdentityStatus.ACTIVE
                ):
                    raise AuthorizationError("el propietario USER no está verificado")

                agent = unit.agent_identity.get_agent_by_identity_id(agent_identity_id)
                if (
                    agent is None
                    or agent.identity.identity_id != agent_identity_id
                    or agent.identity.status is not IdentityStatus.ACTIVE
                ):
                    raise AuthorizationError("la identidad AGENT no está activa")
                if not unit.native_agent_identity.has_active_native_agent_binding(
                    agent_identity_id,
                    verified_owner_identity.issuer_id,
                ):
                    raise AuthorizationError("el AGENT no tiene un binding nativo activo")

                grant = unit.grants.get(grant_id)
                if grant is None:
                    raise NotFoundError("Grant no encontrado")
                if not isinstance(grant, Grant):
                    raise ContractError("el repositorio devolvió un Grant inválido")
                if (
                    grant.grant_id != grant_id
                    or grant.owner_user_id != owner.user_id
                    or grant.subject_identity_id != agent_identity_id
                    or grant.revoked_at is not None
                    or grant.issued_at > now
                    or grant.expires_at <= now
                ):
                    raise AuthorizationError("el Grant no está vigente para este propietario y AGENT")
                if (
                    scope.resource_type != grant.resource_type
                    or not scope.resource_ids.issubset(grant.resource_ids)
                    or not scope.actions.issubset(grant.actions)
                ):
                    raise AuthorizationError("el alcance solicitado excede el Grant")
                if not_before < grant.issued_at or expires_at > grant.expires_at:
                    raise AuthorizationError("la ventana de delegación excede la vigencia del Grant")

                delegation = AgentDelegation(
                    delegation_id=str(uuid4()),
                    owner_user_id=owner.user_id,
                    owner_identity_id=owner.identity.identity_id,
                    agent_identity_id=agent.identity.identity_id,
                    grant_id=grant.grant_id,
                    grant_revision=grant.revision,
                    project_id=grant.project_id,
                    environment=grant.environment,
                    scope=scope,
                    issuer_id=verified_owner_identity.issuer_id,
                    issued_at=now,
                    not_before=not_before,
                    expires_at=expires_at,
                    created_by_user_identity_id=owner.identity.identity_id,
                )
                unit.agent_delegations.create(delegation)
                unit.commit()
                return delegation
        except (AuthorizationError, ContractError, NotFoundError):
            raise

    def revoke_delegation(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        verified_owner_identity: VerifiedIdentityContext,
    ) -> AgentDelegation:
        """Revoke an existing delegation after revalidating its canonical owner."""
        validate_canonical_uuid4(delegation_id, "delegation_id")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser entero positivo")
        if not isinstance(verified_owner_identity, VerifiedIdentityContext):
            raise AuthorizationError("se requiere evidencia USER verificada")

        try:
            with self._uow_factory() as unit:
                owner = self._owner_verifier.verify_in_unit_of_work(
                    verified_owner_identity, unit
                )
                if (
                    owner.user_id != verified_owner_identity.user_id
                    or owner.identity.identity_id != verified_owner_identity.identity_id
                    or owner.identity.status is not IdentityStatus.ACTIVE
                ):
                    raise AuthorizationError("el propietario USER no está verificado")

                delegation = unit.agent_delegations.get(delegation_id)
                if delegation is None:
                    raise NotFoundError("delegación no encontrada")
                if (
                    delegation.owner_user_id != owner.user_id
                    or delegation.owner_identity_id != owner.identity.identity_id
                ):
                    raise AuthorizationError(
                        "el propietario verificado no puede revocar esta delegación"
                    )

                revoked_at = self._clock.now()
                _require_utc(revoked_at, "clock.now()")
                revoked = unit.agent_delegations.revoke(
                    delegation_id,
                    expected_revision=expected_revision,
                    revoked_at=revoked_at,
                    revoked_by_user_id=owner.user_id,
                )
                unit.commit()
                return revoked
        except (AuthorizationError, ContractError, NotFoundError):
            raise
