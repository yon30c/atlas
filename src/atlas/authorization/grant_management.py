"""Servicio de administración de Grants y orquestación de revocaciones."""

from datetime import datetime, timedelta

from atlas.authorization.grant_revocation import (
    GrantRevocationAuthorityChangeAuthorization,
    GrantRevocationAuthorizationStatus,
    GrantRevocationProofAuthorizationService,
    GrantRevocationResult,
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
from atlas.core.identity import IdentityKind, IdentityStatus
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
from atlas.ports.grants import GrantRepository


class GrantManagementService:
    """Administra Grants; la revocación nunca escribe directamente el repositorio."""

    def __init__(
        self,
        repository: GrantRepository,
        *,
        consumer_id: str,
        revocation_authorizer: GrantRevocationAuthorizationPort,
        proof_authorization: GrantRevocationProofAuthorizationService,
        change_coordinator: AuthorityChangeCoordinatorPort,
    ) -> None:
        if not isinstance(consumer_id, str) or not consumer_id.strip():
            raise ContractError("consumer_id debe ser una cadena no vacía")
        if (
            revocation_authorizer is None
            or proof_authorization is None
            or change_coordinator is None
        ):
            raise ContractError("los puertos de revocación son obligatorios")
        self._repository = repository
        self._consumer_id = consumer_id
        self._revocation_authorizer = revocation_authorizer
        self._proof_authorization = proof_authorization
        self._change_coordinator = change_coordinator

    def issue(
        self,
        context: OperationContext,
        grant: Grant,
        now: datetime,
    ) -> Grant:
        """Emite un Grant si el actor es su propietario."""
        self._validate_owner_context(context)
        self._validate_utc(now)
        if not isinstance(grant, Grant):
            raise ContractError("grant debe ser Grant")
        if grant.owner_user_id != context.user_id:
            raise AuthorizationError(
                "No se pueden emitir Grants para otro propietario"
            )
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
        if self._repository.get(grant.grant_id) is not None:
            raise ContractError("El grant_id ya existe")
        self._repository.create(grant)
        return grant

    def revoke(
        self,
        context: OperationContext,
        grant_id: str,
        idempotency_key: str,
        now: datetime,
    ) -> GrantRevocationResult:
        """Solicita autorización CAM y delega el cambio al coordinador durable."""
        self._validate_owner_context(context)
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
        if grant.owner_user_id != context.user_id:
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
            return self._to_grant_result(existing, grant)

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
                return self._to_grant_result(recovered, grant)
            raise ContractError(
                "Reserva indeterminada; reintentar con la misma idempotency_key"
            ) from exc
        if reservation is None:
            raise ContractError(
                "No se pudo reservar la operación; reintentar con la misma idempotency_key"
            )
        self._validate_reservation(reservation, intent)

        if reservation.status is not AuthorityChangeStatus.REQUESTED:
            existing_result = self._change_coordinator.get_result(
                reservation.operation_id
            )
            if existing_result is None:
                return self._blocked_result(reservation)
            return self._to_grant_result(existing_result, grant)

        authorization_request = GrantRevocationAuthorizationRequest(
            request_id=context.request_id,
            actor_identity_id=context.actor.identity_id,
            owner_user_id=grant.owner_user_id,
            grant_id=grant.grant_id,
            expected_revision=grant.revision,
            requested_at=now,
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
            return self._abort_unstarted(reservation, now, grant)

        try:
            proof_result = self._proof_authorization.verify_and_consume(
                request=authorization_request,
                evidence=evidence,
                operation_id=reservation.operation_id,
                idempotency_key=idempotency_key,
                now=now,
            )
        except Exception:
            # No abortar: el consumo pudo confirmarse y perderse su respuesta.
            return self._blocked_result(reservation)
        if not isinstance(proof_result, GrantRevocationAuthorizationResult):
            return self._blocked_result(reservation)
        if not proof_result.authorized:
            if proof_result.status in (
                GrantRevocationAuthorizationStatus.DENIED,
                GrantRevocationAuthorizationStatus.PROOF_REPLAY_CONFLICT,
            ):
                return self._abort_unstarted(reservation, now, grant)
            # Verificador no disponible o consumo incierto: conservar la misma
            # operación para recuperación con la misma clave, nunca abortarla.
            return self._blocked_result(reservation)

        authorization = GrantRevocationAuthorityChangeAuthorization(
            operation_id=reservation.operation_id,
            request=authorization_request,
            evidence=evidence,
            authorization_result=proof_result,
            proposed_revision=grant.revision + 1,
            consumed_at=now,
        )
        try:
            change_result = self._change_coordinator.apply_change(
                reservation,
                authorization,
                now,
            )
        except Exception:
            # Resolver el resultado durable; nunca inferir rollback por timeout.
            change_result = None
        if change_result is None:
            change_result = self._change_coordinator.get_result(
                reservation.operation_id
            )
        if change_result is None:
            return self._blocked_result(reservation)
        return self._to_grant_result(change_result, grant)

    def _abort_unstarted(
        self,
        reservation: AuthorityChangeReservation,
        now: datetime,
        original_grant: Grant,
    ) -> GrantRevocationResult:
        result = self._change_coordinator.abort_unstarted(reservation, now)
        if result is None:
            return self._blocked_result(reservation)
        return self._to_grant_result(result, original_grant)

    def _to_grant_result(
        self,
        result: AuthorityChangeResult,
        original_grant: Grant,
    ) -> GrantRevocationResult:
        if not isinstance(result, AuthorityChangeResult):
            return self._blocked_for_grant(original_grant)

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
            current = self._repository.get(original_grant.grant_id)
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
            raise ContractError("el coordinador debe devolver AuthorityChangeReservation")
        if reservation.intent != intent:
            raise ContractError("la reserva no corresponde a la intención exacta")

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

    @staticmethod
    def _validate_owner_context(context: OperationContext) -> None:
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")

        actor = context.actor
        if (
            actor.kind is not IdentityKind.USER
            or actor.status is not IdentityStatus.ACTIVE
            or actor.identity_id != context.user_id
            or context.delegation is not None
        ):
            raise AuthorizationError(
                "Se requiere una acción directa de un usuario propietario activo"
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
