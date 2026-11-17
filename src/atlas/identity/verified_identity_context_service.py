"""Identity Authority admission of native proofs and verification of contexts."""

from dataclasses import replace
from datetime import datetime, timedelta
import secrets
from typing import Protocol
from uuid import uuid4

from atlas.core.errors import AtlasError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.native_identity import (
    NativeIdentityBindingStatus,
    NativeIssuerProfile,
    NativeIssuerStatus,
)
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.authentication.native import NativeProofReference
from atlas.ports.clock import Clock
from atlas.ports.verified_identity_context_attestor import (
    VerifiedIdentityContextAttestorPort,
)


class VerifiedIdentityContextRejected(AtlasError):
    """A proof or context is invalid, expired, replayed, or no longer current."""


class VerifiedIdentityContextUnavailable(AtlasError):
    """A required authority or cryptographic dependency is unavailable."""


class _IdentityUnitOfWork(Protocol):
    identity: object
    native_identity: object
    native_authentication: object

    def __enter__(self): ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...


class IdentityUnitOfWorkFactory(Protocol):
    def __call__(self) -> _IdentityUnitOfWork: ...


class VerifiedIdentityContextService:
    """Consumes native proofs and issues short-lived, HMAC-attested USER contexts.

    Proof consumption, binding lookup, and canonical identity resolution share
    one physical SQLiteLocalAuthorityUnitOfWork. No endpoint or login flow is
    exposed by this application service.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: IdentityUnitOfWorkFactory,
        clock: Clock,
        attestor: VerifiedIdentityContextAttestorPort,
        realm: str,
        audience: str,
        context_ttl: timedelta,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")
        if not callable(getattr(attestor, "sign", None)) or not callable(
            getattr(attestor, "verify", None)
        ):
            raise ContractError("attestor no implementa sign/verify")
        if not isinstance(realm, str) or not realm:
            raise ContractError("realm confiable debe ser no vacío")
        if not isinstance(audience, str) or not audience:
            raise ContractError("audience confiable debe ser no vacía")
        if not isinstance(context_ttl, timedelta) or not (
            timedelta(0) < context_ttl <= timedelta(minutes=5)
        ):
            raise ContractError("context_ttl debe estar entre 0 y 5 minutos")
        self._uow_factory = unit_of_work_factory
        self._clock = clock
        self._attestor = attestor
        self._realm = realm
        self._audience = audience
        self._context_ttl = context_ttl

    def _now(self) -> datetime:
        value = self._clock.now()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise VerifiedIdentityContextUnavailable("reloj UTC no disponible")
        return value

    def admit_proof(
        self, reference: NativeProofReference
    ) -> VerifiedIdentityContext:
        """Consume a one-shot proof and resolve its canonical USER identity."""
        if not isinstance(reference, NativeProofReference):
            raise ContractError("reference debe ser NativeProofReference")
        consumed_at = self._now()
        context = None
        no_proof = False
        try:
            with self._uow_factory() as unit:
                proof = unit.native_authentication.consume_native_authentication_proof(
                    reference,
                    expected_audience=self._audience,
                    consumed_at=consumed_at,
                )
                if proof is None:
                    # Persist terminal EXPIRED/REVOKED proof states if the adapter
                    # changed them; invalid references remain a no-op.
                    unit.commit()
                    no_proof = True
                else:
                    issuer = unit.native_identity.get_native_issuer(self._realm)
                    if (
                        issuer is None
                        or issuer.issuer_id != proof.issuer_id
                        or issuer.profile is not NativeIssuerProfile.NATIVE_AUTHORITY_PROOF
                        or issuer.status is not NativeIssuerStatus.ACTIVE
                    ):
                        raise VerifiedIdentityContextRejected(
                            "prueba de identidad no válida"
                        )

                    binding = unit.native_identity.get_native_binding(
                        issuer.issuer_id, proof.native_subject.digest
                    )
                    if (
                        binding is None
                        or binding.status is not NativeIdentityBindingStatus.ACTIVE
                        or binding.issuer_id != proof.issuer_id
                    ):
                        raise VerifiedIdentityContextRejected(
                            "prueba de identidad no válida"
                        )

                    canonical = unit.identity.get_user_by_identity_id(
                        binding.identity_id
                    )
                    if (
                        canonical is None
                        or canonical.identity.identity_id != binding.identity_id
                        or canonical.identity.kind is not IdentityKind.USER
                        or canonical.identity.status is not IdentityStatus.ACTIVE
                    ):
                        raise VerifiedIdentityContextRejected(
                            "prueba de identidad no válida"
                        )

                    verified_at = self._now()
                    expires_at = verified_at + self._context_ttl
                    provisional = VerifiedIdentityContext(
                        context_id=str(uuid4()),
                        identity_id=canonical.identity.identity_id,
                        identity_type=IdentityKind.USER,
                        identity_revision=canonical.identity.revision,
                        user_id=canonical.user_id,
                        binding_id=binding.binding_id,
                        binding_revision=binding.revision,
                        issuer_id=issuer.issuer_id,
                        authenticated_at=proof.authenticated_at,
                        verified_at=verified_at,
                        expires_at=expires_at,
                        verification_ref=secrets.token_urlsafe(32),
                        # A valid-shaped placeholder is excluded from the payload.
                        attestation=secrets.token_urlsafe(32),
                    )
                    signature = self._attestor.sign(provisional.attestation_payload())
                    context = replace(provisional, attestation=signature)
                    unit.commit()

            if no_proof or context is None:
                raise VerifiedIdentityContextRejected(
                    "prueba de identidad no válida"
                )
            return context
        except (VerifiedIdentityContextRejected, ContractError):
            raise
        except Exception as exc:
            raise VerifiedIdentityContextUnavailable(
                "Identity Authority no pudo verificar la prueba"
            ) from exc

    def verify(
        self, context: VerifiedIdentityContext
    ) -> CanonicalUserIdentity:
        """Revalidate attestation, expiry, issuer, binding and canonical identity."""
        if not isinstance(context, VerifiedIdentityContext):
            raise VerifiedIdentityContextRejected("contexto de identidad no válido")
        now = self._now()
        if (
            context.expires_at <= now
            or context.verified_at > now
            or context.authenticated_at > context.verified_at
            or context.expires_at - context.verified_at > self._context_ttl
        ):
            raise VerifiedIdentityContextRejected("contexto de identidad no válido")
        try:
            if not self._attestor.verify(
                context.attestation_payload(), context.attestation
            ):
                raise VerifiedIdentityContextRejected(
                    "contexto de identidad no válido"
                )
            with self._uow_factory() as unit:
                issuer = unit.native_identity.get_native_issuer(self._realm)
                if (
                    issuer is None
                    or issuer.issuer_id != context.issuer_id
                    or issuer.profile is not NativeIssuerProfile.NATIVE_AUTHORITY_PROOF
                    or issuer.status is not NativeIssuerStatus.ACTIVE
                ):
                    raise VerifiedIdentityContextRejected(
                        "contexto de identidad no válido"
                    )

                binding = unit.native_identity.get_native_binding_by_id(
                    context.binding_id
                )
                if (
                    binding is None
                    or binding.status is not NativeIdentityBindingStatus.ACTIVE
                    or binding.issuer_id != context.issuer_id
                    or binding.identity_id != context.identity_id
                    or binding.revision != context.binding_revision
                ):
                    raise VerifiedIdentityContextRejected(
                        "contexto de identidad no válido"
                    )

                canonical = unit.identity.get_user_by_identity_id(
                    context.identity_id
                )
                if (
                    canonical is None
                    or canonical.user_id != context.user_id
                    or canonical.identity.identity_id != context.identity_id
                    or canonical.identity.kind is not IdentityKind.USER
                    or canonical.identity.status is not IdentityStatus.ACTIVE
                    or canonical.identity.revision != context.identity_revision
                ):
                    raise VerifiedIdentityContextRejected(
                        "contexto de identidad no válido"
                    )
                return canonical
        except VerifiedIdentityContextRejected:
            raise
        except Exception as exc:
            raise VerifiedIdentityContextUnavailable(
                "Identity Authority no pudo revalidar el contexto"
            ) from exc
