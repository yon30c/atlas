
"""Servicio de solicitudes, aprobación y rechazo de renovaciones."""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from atlas.authorization.agent_renewal_policy import require_agent_renewal_cam_allow
from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.identity_evidence import (
    require_verified_owner_context_in_unit_of_work,
)
from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    RenewalStatus,
)
from atlas.core.context import OperationContext
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.errors import (
    AuthorizationError,
    ConcurrencyError,
    ContractError,
    NotFoundError,
)
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationStatus,
    VerifiedAgentDelegationContext,
)
from atlas.ports.clock import Clock
from atlas.ports.verified_agent_identity_context_verifier import VerifiedAgentIdentityContextVerifierPort
from atlas.ports.verified_agent_delegation_context_verifier import VerifiedAgentDelegationContextVerifierPort
from atlas.ports.verified_identity_context_verifier import (
    VerifiedIdentityContextVerifierPort,
)
from atlas.ports.authorization_unit_of_work import AuthorizationUnitOfWork
from atlas.ports.grant_renewals import GrantRenewalRepository
from atlas.ports.grants import GrantRepository


class GrantRenewalService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], AuthorizationUnitOfWork],
        *,
        identity_verifier: VerifiedIdentityContextVerifierPort | None = None,
        agent_identity_verifier: VerifiedAgentIdentityContextVerifierPort | None = None,
        delegation_context_verifier: VerifiedAgentDelegationContextVerifierPort | None = None,
        clock: Clock | None = None,
        evaluator: AuthorizationEvaluator | None = None,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        self._unit_of_work_factory = unit_of_work_factory
        self._identity_verifier = identity_verifier
        self._agent_identity_verifier = agent_identity_verifier
        self._delegation_context_verifier = delegation_context_verifier
        self._clock = clock
        self._evaluator = evaluator or AuthorizationEvaluator()

    def request_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        grant_id: str,
        proposed_expires_at: datetime,
        now: datetime | None = None,
        *,
        verified_agent_identity: VerifiedAgentIdentityContext | None = None,
        verified_delegation: VerifiedAgentDelegationContext | None = None,
    ) -> GrantRenewalRequest:
        """Create an AGENT renewal request after same-UoW evidence and CAM checks.

        The legacy positional now parameter is intentionally ignored.
        Security time is obtained only from the trusted injected Clock.
        """
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if (
            not isinstance(verified_agent_identity, VerifiedAgentIdentityContext)
            or not isinstance(verified_delegation, VerifiedAgentDelegationContext)
        ):
            raise AuthorizationError(
                "Solicitud AGENT requiere evidencia de identidad y delegación verificable"
            )
        if (
            self._agent_identity_verifier is None
            or not callable(getattr(self._agent_identity_verifier, "verify_in_unit_of_work", None))
            or self._delegation_context_verifier is None
            or not callable(getattr(self._delegation_context_verifier, "verify_in_unit_of_work", None))
            or self._clock is None
            or not callable(getattr(self._clock, "now", None))
        ):
            raise AuthorizationError("La autoridad AGENT de renovación no está configurada")

        self._validate_identifier(renewal_id, "renewal_id")
        self._validate_identifier(grant_id, "grant_id")
        self._validate_utc(proposed_expires_at, "proposed_expires_at")
        trusted_now = self._clock.now()
        self._validate_utc(trusted_now, "clock.now()")

        with self._unit_of_work_factory() as uow:
            required_repositories = (
                "agent_identity", "agent_delegations", "native_agent_identity",
                "native_identity", "identity", "project_environments",
                "project_environment_associations", "grants", "renewals",
            )
            if any(getattr(uow, name, None) is None for name in required_repositories):
                raise AuthorizationError(
                    "Se requiere SQLiteLocalAuthorityUnitOfWork con autoridades canónicas compartidas"
                )

            canonical_agent = self._agent_identity_verifier.verify_in_unit_of_work(
                verified_agent_identity, uow
            )
            canonical_delegation = self._delegation_context_verifier.verify_in_unit_of_work(
                verified_delegation, uow
            )
            if (
                canonical_agent.identity != context.actor
                or canonical_delegation.delegation_id != verified_delegation.delegation_id
                or canonical_delegation.revision != verified_delegation.delegation_revision
                or canonical_delegation.owner_user_id != verified_delegation.owner_user_id
                or canonical_delegation.owner_identity_id != verified_delegation.owner_identity_id
                or canonical_delegation.agent_identity_id != verified_delegation.agent_identity_id
                or canonical_delegation.grant_id != verified_delegation.grant_id
                or canonical_delegation.grant_revision != verified_delegation.grant_revision
                or canonical_delegation.project_id != verified_delegation.project_id
                or canonical_delegation.environment != verified_delegation.environment
                or canonical_delegation.scope != verified_delegation.scope
                or canonical_delegation.issuer_id != verified_delegation.issuer_id
                or canonical_delegation.status.value != "active"
                or not (
                    canonical_delegation.not_before <= trusted_now
                    < canonical_delegation.expires_at
                )
            ):
                raise AuthorizationError("la evidencia AGENT/delegación no coincide con el estado canónico")

            grant = self._get_grant(uow.grants, grant_id)
            if (
                canonical_delegation.grant_id != grant.grant_id
                or canonical_delegation.grant_revision != grant.revision
                or canonical_delegation.owner_user_id != grant.owner_user_id
                or canonical_delegation.agent_identity_id != grant.subject_identity_id
            ):
                raise AuthorizationError("la delegación no corresponde al Grant actual")

            project = uow.project_environments.get_project(grant.project_id)
            environment = uow.project_environments.get_environment(grant.environment)
            association = uow.project_environment_associations.get_association(
                grant.project_id, grant.environment
            )
            if (
                project is None or project.status != "active"
                or str(project.project_id) != grant.project_id
                or environment is None or environment.status != "active"
                or str(environment.environment_id) != grant.environment
                or association is None
                or association.status.value != "active"
                or str(association.project_id) != grant.project_id
                or str(association.environment_id) != grant.environment
            ):
                raise AuthorizationError(
                    "Project/Environment no existe, no está activo o no está asociado"
                )

            self._validate_grant_active(grant, trusted_now)
            if proposed_expires_at <= grant.expires_at:
                raise ContractError(
                    "proposed_expires_at debe extender el vencimiento actual del Grant"
                )

            require_agent_renewal_cam_allow(
                context=context,
                verified_agent_identity=verified_agent_identity,
                verified_delegation=verified_delegation,
                grant=grant,
                evaluator=self._evaluator,
                now=trusted_now,
            )

            candidate = GrantRenewalRequest(
                renewal_id=renewal_id,
                grant_id=grant.grant_id,
                owner_user_id=grant.owner_user_id,
                subject_identity_id=grant.subject_identity_id,
                requested_by_identity_id=canonical_agent.identity.identity_id,
                current_expires_at=grant.expires_at,
                proposed_expires_at=proposed_expires_at,
                requested_at=trusted_now,
                grant_revision=grant.revision,
                delegation_id=canonical_delegation.delegation_id,
                delegation_revision=canonical_delegation.revision,
            )

            existing = uow.renewals.get(renewal_id)
            if existing is not None:
                same_intent = (
                    existing.grant_id == candidate.grant_id
                    and existing.owner_user_id == candidate.owner_user_id
                    and existing.subject_identity_id == candidate.subject_identity_id
                    and existing.requested_by_identity_id == candidate.requested_by_identity_id
                    and existing.current_expires_at == candidate.current_expires_at
                    and existing.proposed_expires_at == candidate.proposed_expires_at
                    and existing.grant_revision == candidate.grant_revision
                    and existing.delegation_id == candidate.delegation_id
                    and existing.delegation_revision == candidate.delegation_revision
                )
                if same_intent and existing.status is RenewalStatus.PENDING:
                    return existing
                raise ContractError("renewal_id ya está asociado a otra solicitud")

            pending = tuple(
                item for item in uow.renewals.list_by_grant(grant.grant_id)
                if item.status is RenewalStatus.PENDING
            )
            if pending:
                raise AuthorizationError("ya existe una solicitud PENDING para este Grant")

            uow.renewals.create(candidate)
            uow.commit()
            return candidate

    def approve_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        now: datetime,
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> Grant:
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            canonical = self._validate_owner_context(
                context, verified_identity, uow
            )
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant, canonical)
            self._require_pending(request)
            self._validate_renewal_grant_binding(request, grant)

            if (
                request.grant_revision is not None
                and request.grant_revision != grant.revision
            ):
                raise ContractError(
                    "La revisión del Grant cambió desde la solicitud AGENT"
                )
            if grant.expires_at != request.current_expires_at:
                raise ContractError(
                    "El vencimiento del Grant cambió desde la solicitud"
                )

            decision_time = now
            if request.delegation_id is not None:
                decision_time = self._require_current_agent_renewal_authority(
                    uow, request, grant
                )

            self._validate_grant_active(grant, decision_time)

            expected_version = request.version
            updated_grant = replace(
                grant,
                expires_at=request.proposed_expires_at,
                revision=grant.revision + 1,
            )
            approved_request = replace(
                request,
                status=RenewalStatus.APPROVED,
                decided_at=decision_time,
                decided_by_user_id=canonical.user_id,
                version=expected_version + 1,
            )

            uow.grants.update(updated_grant)
            updated = uow.renewals.update_if_version(
                approved_request,
                expected_version,
            )
            if not updated:
                raise ConcurrencyError(
                    "La solicitud cambió durante la aprobación"
                )
            uow.commit()

        return updated_grant

    def reject_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        now: datetime,
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> GrantRenewalRequest:
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            canonical = self._validate_owner_context(
                context, verified_identity, uow
            )
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant, canonical)
            self._require_pending(request)
            self._validate_renewal_grant_binding(request, grant)

            expected_version = request.version
            rejected_request = replace(
                request,
                status=RenewalStatus.REJECTED,
                decided_at=now,
                decided_by_user_id=canonical.user_id,
                version=expected_version + 1,
            )

            updated = uow.renewals.update_if_version(
                rejected_request,
                expected_version,
            )
            if not updated:
                raise ConcurrencyError(
                    "La solicitud cambió durante el rechazo"
                )
            uow.commit()

        return rejected_request

    def _require_current_agent_renewal_authority(
        self,
        unit_of_work: AuthorizationUnitOfWork,
        request: GrantRenewalRequest,
        grant: Grant,
    ) -> datetime:
        """Revalidate AGENT authority at USER approval time in the shared UoW."""
        required = (
            "agent_delegations", "identity", "agent_identity",
            "native_agent_identity", "project_environments", "project_environment_associations",
        )
        if any(getattr(unit_of_work, name, None) is None for name in required):
            raise AuthorizationError(
                "No están disponibles todas las autoridades para revalidar la renovación AGENT"
            )
        if self._clock is None or not callable(getattr(self._clock, "now", None)):
            raise AuthorizationError("Se requiere reloj confiable para aprobar una solicitud AGENT")
        try:
            decision_time = self._clock.now()
            self._validate_utc(decision_time, "clock.now()")
            delegation = unit_of_work.agent_delegations.get(request.delegation_id)
            if not isinstance(delegation, AgentDelegation):
                raise AuthorizationError("La delegación canónica ya no existe")
            if (
                delegation.status is not AgentDelegationStatus.ACTIVE
                or delegation.revision != request.delegation_revision
                or delegation.delegation_id != request.delegation_id
                or not (delegation.not_before <= decision_time < delegation.expires_at)
                or delegation.grant_id != grant.grant_id
                or delegation.grant_revision != request.grant_revision
                or delegation.grant_revision != grant.revision
                or delegation.owner_user_id != request.owner_user_id
                or delegation.agent_identity_id != request.requested_by_identity_id
                or delegation.agent_identity_id != grant.subject_identity_id
                or delegation.project_id != grant.project_id
                or delegation.environment != grant.environment
                or delegation.scope.resource_type != grant.resource_type
                or delegation.scope.resource_ids != grant.resource_ids
                or "grant.renewal.request" not in delegation.scope.actions
                or "grant.renewal.request" not in grant.actions
                or delegation.expires_at > grant.expires_at
            ):
                raise AuthorizationError(
                    "La delegación AGENT fue revocada, cambió o ya no cubre exactamente el Grant"
                )

            owner = unit_of_work.identity.get_user_by_identity_id(
                delegation.owner_identity_id
            )
            agent = unit_of_work.agent_identity.get_agent_by_identity_id(
                delegation.agent_identity_id
            )
            if (
                owner is None
                or owner.user_id != delegation.owner_user_id
                or owner.identity.kind is not IdentityKind.USER
                or owner.identity.status is not IdentityStatus.ACTIVE
                or agent is None
                or agent.identity.identity_id != delegation.agent_identity_id
                or agent.identity.kind is not IdentityKind.AGENT
                or agent.identity.status is not IdentityStatus.ACTIVE
                or not unit_of_work.native_agent_identity.has_active_native_agent_binding(
                    delegation.agent_identity_id, delegation.issuer_id
                )
            ):
                raise AuthorizationError(
                    "La identidad owner, AGENT o su binding nativo ya no está activo"
                )

            project = unit_of_work.project_environments.get_project(grant.project_id)
            environment = unit_of_work.project_environments.get_environment(grant.environment)
            association = unit_of_work.project_environment_associations.get_association(
                grant.project_id, grant.environment
            )
            if (
                project is None or project.status != "active"
                or str(project.project_id) != grant.project_id
                or environment is None or environment.status != "active"
                or str(environment.environment_id) != grant.environment
                or association is None
                or association.status.value != "active"
                or str(association.project_id) != grant.project_id
                or str(association.environment_id) != grant.environment
            ):
                raise AuthorizationError(
                    "La asociación Project/Environment ya no está activa"
                )
            return decision_time
        except AuthorizationError:
            raise
        except Exception as exc:
            raise AuthorizationError(
                "No se pudo revalidar la autoridad AGENT dentro de la transacción"
            ) from exc

    @staticmethod
    def _get_grant(
        repository: GrantRepository,
        grant_id: str,
    ) -> Grant:
        grant = repository.get(grant_id)
        if grant is None:
            raise NotFoundError("Grant no encontrado")
        if not isinstance(grant, Grant):
            raise ContractError("El repositorio debe devolver un Grant")
        return grant

    @staticmethod
    def _get_renewal(
        repository: GrantRenewalRepository,
        renewal_id: str,
    ) -> GrantRenewalRequest:
        request = repository.get(renewal_id)
        if request is None:
            raise NotFoundError("Solicitud de renovación no encontrada")
        if not isinstance(request, GrantRenewalRequest):
            raise ContractError(
                "El repositorio debe devolver una solicitud de renovación"
            )
        return request

    def _validate_owner_context(
        self,
        context: OperationContext,
        verified_identity: VerifiedIdentityContext | None,
        unit_of_work: AuthorizationUnitOfWork,
    ) -> CanonicalUserIdentity:
        return require_verified_owner_context_in_unit_of_work(
            context,
            verified_identity,
            self._identity_verifier,
            unit_of_work,
        )

    @staticmethod
    def _validate_scope(
        context: OperationContext,
        grant: Grant,
    ) -> None:
        if context.project_id != grant.project_id:
            raise AuthorizationError(
                "El proyecto del contexto no coincide con el Grant"
            )
        if context.environment != grant.environment:
            raise AuthorizationError(
                "El entorno del contexto no coincide con el Grant"
            )

    def _validate_owner_and_scope(
        self,
        context: OperationContext,
        request: GrantRenewalRequest,
        grant: Grant,
        canonical: CanonicalUserIdentity,
    ) -> None:
        if (
            canonical.user_id != request.owner_user_id
            or canonical.user_id != grant.owner_user_id
        ):
            raise AuthorizationError(
                "Solo el propietario puede decidir la renovación"
            )
        self._validate_scope(context, grant)

    @staticmethod
    def _validate_renewal_grant_binding(
        request: GrantRenewalRequest,
        grant: Grant,
    ) -> None:
        if (
            request.grant_id != grant.grant_id
            or request.owner_user_id != grant.owner_user_id
            or request.subject_identity_id != grant.subject_identity_id
            or request.requested_by_identity_id != grant.subject_identity_id
        ):
            raise ContractError(
                "El Grant ya no corresponde a la solicitud de renovación"
            )

    @staticmethod
    def _validate_grant_active(grant: Grant, now: datetime) -> None:
        if not (
            grant.issued_at <= now < grant.expires_at
            and (grant.revoked_at is None or grant.revoked_at > now)
        ):
            raise AuthorizationError(
                "El Grant debe estar vigente y no revocado"
            )

    @staticmethod
    def _require_pending(request: GrantRenewalRequest) -> None:
        if request.status is not RenewalStatus.PENDING:
            raise ContractError(
                "La solicitud de renovación ya fue decidida"
            )

    @staticmethod
    def _validate_identifier(value: str, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} debe ser una cadena no vacía")

    @staticmethod
    def _validate_utc(value: datetime, field: str) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContractError(
                f"{field} debe ser un datetime con zona horaria"
            )
        if value.utcoffset() != timedelta(0):
            raise ContractError(f"{field} debe estar en UTC")
