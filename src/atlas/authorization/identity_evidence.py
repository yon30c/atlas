"""Validación común de operaciones directas del propietario USER."""

from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.ports.verified_identity_context_verifier import (
    VerifiedIdentityContextVerifierPort,
)


def require_verified_owner_context(
    context: OperationContext,
    verified_identity: VerifiedIdentityContext | None,
    verifier: VerifiedIdentityContextVerifierPort | None,
) -> CanonicalUserIdentity:
    """Require fresh cryptographic USER evidence matching the operation actor.

    OperationContext fields are attribution data only. This function compares
    them with the canonical pair returned by the trusted verifier; it never
    infers authentication from actor status, IDs, or delegation flags.
    """
    if not isinstance(context, OperationContext):
        raise ContractError("context debe ser OperationContext")
    if not isinstance(verified_identity, VerifiedIdentityContext):
        raise AuthorizationError("Se requiere evidencia vigente del propietario")
    if verifier is None or not callable(getattr(verifier, "verify", None)):
        raise AuthorizationError("La verificación de identidad no está disponible")
    try:
        canonical = verifier.verify(verified_identity)
    except Exception as exc:
        raise AuthorizationError(
            "La identidad del propietario no pudo verificarse"
        ) from exc
    if (
        not isinstance(canonical, CanonicalUserIdentity)
        or canonical.identity.kind is not IdentityKind.USER
        or canonical.identity.status is not IdentityStatus.ACTIVE
        or verified_identity.identity_type is not IdentityKind.USER
        or verified_identity.identity_id != canonical.identity.identity_id
        or verified_identity.identity_revision != canonical.identity.revision
        or verified_identity.user_id != canonical.user_id
        or context.actor != canonical.identity
        or context.user_id != canonical.user_id
        or context.delegation is not None
    ):
        raise AuthorizationError(
            "El contexto no corresponde a la identidad canónica del propietario"
        )
    return canonical


def require_verified_owner_context_in_unit_of_work(
    context: OperationContext,
    verified_identity: VerifiedIdentityContext | None,
    verifier: VerifiedIdentityContextVerifierPort | None,
    unit,
) -> CanonicalUserIdentity:
    """Require canonical USER evidence revalidated in the caller's transaction."""
    if not isinstance(context, OperationContext):
        raise ContractError("context debe ser OperationContext")
    if not isinstance(verified_identity, VerifiedIdentityContext):
        raise AuthorizationError("Se requiere evidencia vigente del propietario")
    verify_in_uow = getattr(verifier, "verify_in_unit_of_work", None)
    if not callable(verify_in_uow):
        raise AuthorizationError(
            "La verificación transaccional de identidad no está disponible"
        )
    try:
        canonical = verify_in_uow(verified_identity, unit)
    except Exception as exc:
        raise AuthorizationError(
            "La identidad del propietario no pudo verificarse en la transacción"
        ) from exc
    if (
        not isinstance(canonical, CanonicalUserIdentity)
        or canonical.identity.kind is not IdentityKind.USER
        or canonical.identity.status is not IdentityStatus.ACTIVE
        or verified_identity.identity_type is not IdentityKind.USER
        or verified_identity.identity_id != canonical.identity.identity_id
        or verified_identity.identity_revision != canonical.identity.revision
        or verified_identity.user_id != canonical.user_id
        or context.actor != canonical.identity
        or context.user_id != canonical.user_id
        or context.delegation is not None
    ):
        raise AuthorizationError(
            "El contexto no corresponde a la identidad canónica del propietario"
        )
    return canonical
