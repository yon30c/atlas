"""Servicio de administración de Grants y orquestación de revocaciones."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

from atlas.authorization.grant_revocation import (
    GrantRevocationAuthorityChangeAuthorization,
    GrantRevocationAuthorizationResult,
    GrantRevocationAuthorizationStatus,
    GrantRevocationProofAuthorizationService,
    GrantRevocationResult,
)
from atlas.authorization.identity_evidence import (
    require_verified_owner_context,
    require_verified_owner_context_in_unit_of_work,
)
from atlas.authorization.models import (
    Grant,
    GrantRevocationAuthorizationRequest,
)
from atlas.core.context import OperationContext
from atlas.core.errors import (
    AuthorizationError,
    ContractError,
    NotFoundError,
)
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.ports.verified_identity_context_verifier import (
    VerifiedIdentityContextVerifierPort,
)
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    AuthorityChangeStatus,
)
from atlas.memory.consistency import AuthorityKind
from atlas.ports.authority_change_coordinator import AuthorityChangeCoordinatorPort
from atlas.ports.grant_revocation_authorization import (
    GrantRevocationAuthorizationPort,
)
from atlas.ports.clock import Clock
from atlas.ports.grants import GrantRepository
from atlas.ports.authorization_unit_of_work import AuthorizationUnitOfWork


class GrantManagementService:
    """Administra Grants; la revocación nunca escribe directamente el repositorio."""

    def __init__(
        self,
        repository: GrantRepository,
        *,
        consumer_id: str | None = None,
        revocation_authorizer: GrantRevocationAuthorizationPort | None = None,
        proof_authorization: GrantRevocationProofAuthorizationService | None = None,
        change_coordinator: AuthorityChangeCoordinatorPort | None = None,
        clock: Clock | None = None,
        unit_of_work_factory: Callable[[], AuthorizationUnitOfWork] | None = None,
        identity_verifier: VerifiedIdentityContextVerifierPort | None = None,
    ) -> None:
        configured = (
            consumer_id is not None,
            revocation_authorizer is not None,
            proof_authorization is not None,
            change_coordinator is not None,
            clock is not None,
        )
        if any(configured) and not all(configured):
            raise ContractError(
                "la configuración de revocación debe proporcionar todos sus puertos"
            )
        if consumer_id is not None and (
            not isinstance(consumer_id, str) or not consumer_id.strip()
        ):
            raise ContractError("consumer_id debe ser una cadena no vacía")
        if unit_of_work_factory is not None and not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._identity_verifier = identity_verifier
        self._consumer_id = cast(str, consumer_id)
        self._revocation_authorizer = cast(
            GrantRevocationAuthorizationPort, revocation_authorizer
        )
        self._proof_authorization = cast(
            GrantRevocationProofAuthorizationService, proof_authorization
        )
        self._change_coordinator = cast(
            AuthorityChangeCoordinatorPort, change_coordinator
        )
        self._clock = cast(Clock, clock)

    def issue(
        self,
        context: OperationContext,
        grant: Grant,
        now: datetime,
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> Grant:
        """Emite un Grant tras revalidar al propietario en la UoW de escritura."""
        self._validate_utc(now)
        if not isinstance(grant, Grant):
            raise ContractError("grant debe ser Grant")
        if grant.project_id != context.project_id:
            raise AuthorizationError(
                "El proyecto del Grant no coincide con el contexto"
            )
        if grant.environment != context.environment:
            raise AuthorizationError(
                "El entorno del Grant no coincide con el contexto"
            )
        if grant.revision != 1:
            raise ContractError("un Grant nuevo debe iniciar en revision 1")
        if grant.issued_at != now:
            raise ContractError(
                "issued_at debe coincidir con el momento de emisión"
            )
        if self._unit_of_work_factory is None:
            raise ContractError(
                "emisión deshabilitada: requiere una unidad de trabajo transaccional"
            )

        # Identity evidence, uniqueness and insertion share one immediate
        # transaction. A suspension/revocation cannot race the Grant write.
        with self._unit_of_work_factory() as uow:
            canonical = require_verified_owner_context_in_unit_of_work(
                context,
                verified_identity,
                self._identity_verifier,
                uow,
            )
            if grant.owner_user_id != canonical.user_id:
                raise AuthorizationError(
                    "No se pueden emitir Grants para otro propietario"
                )
            if uow.grants.get(grant.grant_id) is not None:
                raise ContractError("El grant_id ya existe")
            uow.grants.create(grant)
            uow.commit()
        return grant

    def revoke(
        self,
        context: OperationContext,
        grant_id: str,
        idempotency_key: str,
        now: datetime,
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> GrantRevocationResult:
        """Revoca solo tras verificar al propietario y obtener autorización CAM."""
        canonical = self._validate_owner_context(context, verified_identity)
        if any(
            dependency is None
            for dependency in (
                self._consumer_id,
                self._revocation_authorizer,
                self._proof_authorization,
                self._change_coordinator,
                self._clock,
            )
        ):
            raise ContractError(
                "revocación deshabilitada: faltan los puertos de coordinación y CAM"
            )
        self._validate_utc(now)
        for field, value in (
            ("grant_id", grant_id),
            ("idempotency_key", idempotency_key),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")

        grant = self._repository.get(grant_id)
        if grant is None:
            raise NotFoundError("Grant no encontrado")
        if not isinstance(grant, Grant):
            raise ContractError("El repositorio debe devolver un Grant")
        if grant.owner_user_id != canonical.user_id:
            raise AuthorizationError(
                "No se pueden revocar Grants de otro propietario"
            )

        existing = self._change_coordinator.get_by_idempotency_key(
            self._consumer_id,
            idempotency_key,
        )
        if existing is not None:
            if (
                existing.authority_kind is not AuthorityKind.GRANT
                or existing.authority_id != grant_id
            ):
                raise AuthorizationError(
                    "La clave de idempotencia ya pertenece a otro recurso"
                )
            if existing.status is not AuthorityChangeStatus.REQUESTED:
                return self._to_grant_result(
                    existing, grant, expected_operation_id=existing.operation_id
                )
            reservation = self._change_coordinator.get_reservation(
                existing.operation_id
            )
            if reservation is None:
                return self._blocked_for_grant(
                    grant,
                    operation_id=existing.operation_id,
                    previous_revision=existing.previous_revision,
                    proposed_revision=existing.proposed_revision,
                )
            if (
                reservation.intent.consumer_id != self._consumer_id
                or reservation.intent.idempotency_key != idempotency_key
                or reservation.intent.authority_kind is not AuthorityKind.GRANT
                or reservation.intent.authority_id != grant_id
                or reservation.intent.expected_revision != grant.revision
                or reservation.intent.proposed_revision != grant.revision + 1
            ):
                return self._blocked_for_grant(
                    grant,
                    operation_id=reservation.operation_id,
                    previous_revision=reservation.intent.expected_revision,
                    proposed_revision=reservation.intent.proposed_revision,
                )
        else:
            if grant.revoked_at is not None:
                raise ContractError(
                    "El Grant ya está revocado y no tiene una operación coincidente"
                )

            intent = AuthorityChangeIntent(
                idempotency_key=idempotency_key,
                consumer_id=self._consumer_id,
                authority_kind=AuthorityKind.GRANT,
                authority_id=grant.grant_id,
                expected_revision=grant.revision,
                proposed_revision=grant.revision + 1,
                change_kind="revoke",
                request_context_ref=context.request_id,
                requested_at=now,
            )
            try:
                reservation = self._change_coordinator.reserve_change(intent)
            except Exception as exc:
                # El commit de la reserva puede haberse confirmado aunque se haya
                # perdido la respuesta. Recuperar siempre por la misma clave.
                recovered = self._change_coordinator.get_by_idempotency_key(
                    self._consumer_id,
                    idempotency_key,
                )
                if recovered is not None:
                    if (
                        recovered.authority_kind is AuthorityKind.GRANT
                        and recovered.authority_id == grant_id
                        and recovered.status is AuthorityChangeStatus.REQUESTED
                    ):
                        reservation = self._change_coordinator.get_reservation(
                            recovered.operation_id
                        )
                    else:
                        return self._to_grant_result(
                            recovered, grant,
                            expected_operation_id=recovered.operation_id,
                        )
                else:
                    raise ContractError(
                        "Reserva indeterminada; reintentar con la misma idempotency_key"
                    ) from exc
            if reservation is None:
                raise ContractError(
                    "No se pudo reservar la operación; reintentar con la misma idempotency_key"
                )
            self._validate_reservation(reservation, intent)

        if reservation is None:
            return self._blocked_for_grant(grant)
        if (
            reservation.intent.consumer_id != self._consumer_id
            or reservation.intent.idempotency_key != idempotency_key
            or reservation.intent.authority_kind is not AuthorityKind.GRANT
            or reservation.intent.authority_id != grant_id
            or reservation.intent.expected_revision != grant.revision
            or reservation.intent.proposed_revision != grant.revision + 1
        ):
            return self._blocked_for_grant(
                grant,
                operation_id=reservation.operation_id,
                previous_revision=reservation.intent.expected_revision,
                proposed_revision=reservation.intent.proposed_revision,
            )
        if reservation.status is not AuthorityChangeStatus.REQUESTED:
            existing_result = self._change_coordinator.get_result(
                reservation.operation_id
            )
            if existing_result is None:
                return self._blocked_result(reservation)
            return self._to_grant_result(
                existing_result, grant,
                expected_operation_id=reservation.operation_id,
            )

        authorization_request = GrantRevocationAuthorizationRequest(
            request_id=reservation.intent.request_context_ref,
            actor_identity_id=context.actor.identity_id,
            owner_user_id=grant.owner_user_id,
            grant_id=grant.grant_id,
            expected_revision=grant.revision,
            requested_at=reservation.intent.requested_at,
        )
        try:
            evidence = self._revocation_authorizer.authorize_revocation(
                authorization_request
            )
        except Exception:
            # Una respuesta perdida de CAM no se interpreta como denegación
            # definitiva ni habilita un cambio sin evidencia.
            return self._blocked_result(reservation)

        if evidence is None:
            try:
                abort_at = self._clock.now()
                self._validate_utc(abort_at)
            except Exception:
                return self._blocked_result(reservation)
            return self._abort_unstarted(reservation, abort_at, grant)

        try:
            verification_now = self._clock.now()
            self._validate_utc(verification_now)
        except Exception:
            return self._blocked_result(reservation)

        try:
            authorization = self._proof_authorization.verify_and_consume_for_change(
                request=authorization_request,
                evidence=evidence,
                operation_id=reservation.operation_id,
                idempotency_key=idempotency_key,
                proposed_revision=grant.revision + 1,
                now=verification_now,
            )
        except Exception:
            # No abortar: el consumo pudo confirmarse y perderse su respuesta.
            return self._blocked_result(reservation)
        if isinstance(authorization, GrantRevocationAuthorizationResult):
            if authorization.status in (
                GrantRevocationAuthorizationStatus.DENIED,
                GrantRevocationAuthorizationStatus.PROOF_REPLAY_CONFLICT,
            ):
                return self._abort_unstarted(reservation, verification_now, grant)
            # Verificador no disponible o consumo incierto: conservar la misma
            # operación para recuperación con la misma clave, nunca abortarla.
            return self._blocked_result(reservation)
        if not isinstance(
            authorization,
            GrantRevocationAuthorityChangeAuthorization,
        ):
            return self._blocked_result(reservation)

        try:
            change_result = self._change_coordinator.apply_change(
                reservation,
                authorization,
                verification_now,
            )
        except Exception:
            # Resolver el resultado durable; nunca inferir rollback por timeout.
            change_result = None
        if change_result is None:
            try:
                change_result = self._change_coordinator.get_result(
                    reservation.operation_id
                )
            except Exception:
                change_result = None
        if change_result is None:
            return self._blocked_result(reservation)
        return self._to_grant_result(
            change_result, grant,
            expected_operation_id=reservation.operation_id,
        )

    def _abort_unstarted(
        self,
        reservation: AuthorityChangeReservation,
        now: datetime,
        original_grant: Grant,
    ) -> GrantRevocationResult:
        try:
            result = self._change_coordinator.abort_unstarted(reservation, now)
        except Exception:
            result = None
        if result is None:
            try:
                result = self._change_coordinator.get_result(
                    reservation.operation_id
                )
            except Exception:
                result = None
        if (
            not isinstance(result, AuthorityChangeResult)
            or result.status not in (
                AuthorityChangeStatus.ABORTED,
                AuthorityChangeStatus.BLOCKED,
            )
        ):
            return self._blocked_result(reservation)
        return self._to_grant_result(
            result, original_grant,
            expected_operation_id=reservation.operation_id,
        )

    def _to_grant_result(
        self,
        result: AuthorityChangeResult,
        original_grant: Grant,
        *,
        expected_operation_id: str | None = None,
    ) -> GrantRevocationResult:
        if not isinstance(result, AuthorityChangeResult):
            return self._blocked_for_grant(
                original_grant,
                operation_id=expected_operation_id or "unresolved",
            )
        if (
            expected_operation_id is not None
            and result.operation_id != expected_operation_id
        ):
            return self._blocked_for_grant(
                original_grant,
                operation_id=expected_operation_id,
                previous_revision=original_grant.revision,
                proposed_revision=original_grant.revision + 1,
            )

        if (
            result.authority_kind is not AuthorityKind.GRANT
            or result.authority_id != original_grant.grant_id
        ):
            return self._blocked_for_grant(
                original_grant,
                operation_id=result.operation_id,
                previous_revision=result.previous_revision,
                proposed_revision=result.proposed_revision,
            )

        if (
            result.status is not AuthorityChangeStatus.COMPLETED
            and result.previous_revision != original_grant.revision
        ):
            return self._blocked_for_grant(
                original_grant,
                operation_id=result.operation_id,
                previous_revision=result.previous_revision,
                proposed_revision=result.proposed_revision,
            )

        revoked_grant = None
        status = result.status
        if status is AuthorityChangeStatus.COMPLETED:
            try:
                current = self._repository.get(original_grant.grant_id)
            except Exception:
                current = None
            if (
                not isinstance(current, Grant)
                or current.owner_user_id != original_grant.owner_user_id
                or current.revision != result.proposed_revision
                or current.revoked_at is None
            ):
                status = AuthorityChangeStatus.BLOCKED
            else:
                revoked_grant = current

        return GrantRevocationResult(
            operation_id=result.operation_id,
            grant_id=original_grant.grant_id,
            status=status,
            previous_revision=result.previous_revision,
            proposed_revision=result.proposed_revision,
            revoked_grant=revoked_grant,
        )

    @staticmethod
    def _blocked_for_grant(
        grant: Grant,
        *,
        operation_id: str = "unresolved",
        previous_revision: int | None = None,
        proposed_revision: int | None = None,
    ) -> GrantRevocationResult:
        previous = previous_revision or grant.revision
        proposed = proposed_revision or previous + 1
        return GrantRevocationResult(
            operation_id=operation_id,
            grant_id=grant.grant_id,
            status=AuthorityChangeStatus.BLOCKED,
            previous_revision=previous,
            proposed_revision=proposed,
        )

    @staticmethod
    def _validate_reservation(
        reservation: AuthorityChangeReservation,
        intent: AuthorityChangeIntent,
    ) -> None:
        if not isinstance(reservation, AuthorityChangeReservation):
            raise ContractError(
                "el coordinador debe devolver AuthorityChangeReservation"
            )
        stored = reservation.intent
        if (
            stored.idempotency_key != intent.idempotency_key
            or stored.consumer_id != intent.consumer_id
            or stored.authority_kind is not intent.authority_kind
            or stored.authority_id != intent.authority_id
            or stored.expected_revision != intent.expected_revision
            or stored.proposed_revision != intent.proposed_revision
            or stored.change_kind != intent.change_kind
            or stored.request_context_ref != intent.request_context_ref
        ):
            raise ContractError(
                "la reserva no corresponde a la misma intención idempotente"
            )
        # requested_at es la marca de tiempo original persistida. En un retry
        # puede diferir el reloj del llamador; siempre prevalece la reserva.

    def _blocked_result(
        self,
        reservation: AuthorityChangeReservation,
    ) -> GrantRevocationResult:
        return GrantRevocationResult(
            operation_id=reservation.operation_id,
            grant_id=reservation.intent.authority_id,
            status=AuthorityChangeStatus.BLOCKED,
            previous_revision=reservation.intent.expected_revision,
            proposed_revision=reservation.intent.proposed_revision,
        )

    def _validate_owner_context(
        self,
        context: OperationContext,
        verified_identity: VerifiedIdentityContext | None,
    ) -> CanonicalUserIdentity:
        return require_verified_owner_context(
            context,
            verified_identity,
            self._identity_verifier,
        )

    @staticmethod
    def _validate_utc(value: datetime) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContractError("now debe ser un datetime con zona horaria")
        if value.utcoffset() != timedelta(0):
            raise ContractError("now debe estar en UTC")
