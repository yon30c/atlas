"""Identity Authority admission and verification for native AGENT proofs.

USER and AGENT contexts are deliberately separate types and resolve through
separate canonical identity/binding authorities. Proof consumption, binding
lookup, and canonical AGENT resolution share one local SQLite UoW.
"""

from dataclasses import replace
from datetime import datetime, timedelta
import re
import secrets
from typing import Protocol
from uuid import uuid4

from atlas.authentication.native import NativeProofReference
from atlas.core.errors import AtlasError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.native_identity import NativeIssuerProfile, NativeIssuerStatus
from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext
from atlas.ports.clock import Clock


_REALM_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}", re.ASCII)
_AUDIENCE_RE = re.compile(r"[a-z][a-z0-9._:-]{0,127}", re.ASCII)


class VerifiedAgentIdentityContextRejected(AtlasError):
    """A proof/context is invalid, expired, replayed, or no longer current."""


class VerifiedAgentIdentityContextUnavailable(AtlasError):
    """A required authority or cryptographic dependency is unavailable."""


class _AgentIdentityUnitOfWork(Protocol):
    agent_identity: object
    native_agent_identity: object
    native_identity: object
    native_authentication: object

    def __enter__(self): ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...


class AgentIdentityUnitOfWorkFactory(Protocol):
    def __call__(self) -> _AgentIdentityUnitOfWork: ...


class VerifiedAgentIdentityContextService:
    """Consumes one-shot native proofs and issues short-lived AGENT evidence.

    This service is not a login endpoint, CAM policy engine, or delegation
    authority. Its verify() method is suitable for the AGENT context verifier
    port and always re-reads issuer, binding and canonical identity state.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: AgentIdentityUnitOfWorkFactory,
        clock: Clock,
        attestor,
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
        if not isinstance(realm, str) or _REALM_RE.fullmatch(realm) is None:
            raise ContractError("realm confiable debe ser lowercase ASCII canónico")
        if not isinstance(audience, str) or _AUDIENCE_RE.fullmatch(audience) is None:
            raise ContractError("audience confiable debe ser un identificador interno ASCII")
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

    def _attestation_payload(self, context: VerifiedAgentIdentityContext) -> bytes:
        prefix = (
            b"atlas.verified-agent-identity-context.v1\\x00"
            + self._realm.encode("ascii")
            + b"\\x00"
            + self._audience.encode("ascii")
            + b"\\x00"
        )
        return prefix + context.attestation_payload()

    def _now(self) -> datetime:
        value = self._clock.now()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise VerifiedAgentIdentityContextUnavailable("reloj UTC no disponible")
        return value

    def admit_proof(
        self, reference: NativeProofReference
    ) -> VerifiedAgentIdentityContext:
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
                        raise VerifiedAgentIdentityContextRejected(
                            "prueba de identidad AGENT no válida"
                        )

                    binding = unit.native_agent_identity.get_native_agent_binding(
                        issuer.issuer_id, proof.native_subject.digest
                    )
                    if (
                        binding is None
                        or binding.status.value != "active"
                        or binding.issuer_id != proof.issuer_id
                        or proof.authenticated_at < binding.verified_at
                    ):
                        raise VerifiedAgentIdentityContextRejected(
                            "prueba de identidad AGENT no válida"
                        )

                    canonical = unit.agent_identity.get_agent_by_identity_id(
                        binding.identity_id
                    )
                    if (
                        canonical is None
                        or canonical.identity.identity_id != binding.identity_id
                        or canonical.identity.kind is not IdentityKind.AGENT
                        or canonical.identity.status is not IdentityStatus.ACTIVE
                    ):
                        raise VerifiedAgentIdentityContextRejected(
                            "prueba de identidad AGENT no válida"
                        )

                    verified_at = self._now()
                    provisional = VerifiedAgentIdentityContext(
                        context_id=str(uuid4()),
                        identity_id=canonical.identity.identity_id,
                        identity_type=IdentityKind.AGENT,
                        identity_revision=canonical.identity.revision,
                        binding_id=binding.binding_id,
                        binding_revision=binding.revision,
                        issuer_id=issuer.issuer_id,
                        realm=self._realm,
                        audience=self._audience,
                        authenticated_at=proof.authenticated_at,
                        verified_at=verified_at,
                        expires_at=verified_at + self._context_ttl,
                        verification_ref=secrets.token_urlsafe(32),
                        attestation=secrets.token_urlsafe(32),
                    )
                    signature = self._attestor.sign(
                        self._attestation_payload(provisional)
                    )
                    context = replace(provisional, attestation=signature)
                    unit.commit()

            if no_proof or context is None:
                raise VerifiedAgentIdentityContextRejected(
                    "prueba de identidad AGENT no válida"
                )
            return context
        except (VerifiedAgentIdentityContextRejected, ContractError):
            raise
        except Exception as exc:
            raise VerifiedAgentIdentityContextUnavailable(
                "Identity Authority no pudo verificar la prueba AGENT"
            ) from exc

    def verify(
        self, context: VerifiedAgentIdentityContext
    ) -> CanonicalAgentIdentity:
        if not isinstance(context, VerifiedAgentIdentityContext):
            raise VerifiedAgentIdentityContextRejected("contexto AGENT no válido")
        now = self._now()
        if (
            context.realm != self._realm
            or context.audience != self._audience
            or context.expires_at <= now
            or context.verified_at > now
            or context.authenticated_at > context.verified_at
            or context.expires_at - context.verified_at > self._context_ttl
        ):
            raise VerifiedAgentIdentityContextRejected("contexto AGENT no válido")
        try:
            if not self._attestor.verify(
                self._attestation_payload(context), context.attestation
            ):
                raise VerifiedAgentIdentityContextRejected("contexto AGENT no válido")
            with self._uow_factory() as unit:
                issuer = unit.native_identity.get_native_issuer(self._realm)
                if (
                    issuer is None
                    or issuer.issuer_id != context.issuer_id
                    or issuer.profile is not NativeIssuerProfile.NATIVE_AUTHORITY_PROOF
                    or issuer.status is not NativeIssuerStatus.ACTIVE
                ):
                    raise VerifiedAgentIdentityContextRejected(
                        "contexto AGENT no válido"
                    )

                binding = unit.native_agent_identity.get_native_agent_binding_by_id(
                    context.binding_id
                )
                if (
                    binding is None
                    or binding.status.value != "active"
                    or binding.issuer_id != context.issuer_id
                    or binding.identity_id != context.identity_id
                    or binding.revision != context.binding_revision
                ):
                    raise VerifiedAgentIdentityContextRejected(
                        "contexto AGENT no válido"
                    )

                canonical = unit.agent_identity.get_agent_by_identity_id(
                    context.identity_id
                )
                if (
                    canonical is None
                    or canonical.identity.identity_id != context.identity_id
                    or canonical.identity.kind is not IdentityKind.AGENT
                    or canonical.identity.status is not IdentityStatus.ACTIVE
                    or canonical.identity.revision != context.identity_revision
                ):
                    raise VerifiedAgentIdentityContextRejected(
                        "contexto AGENT no válido"
                    )
                return canonical
        except VerifiedAgentIdentityContextRejected:
            raise
        except Exception as exc:
            raise VerifiedAgentIdentityContextUnavailable(
                "Identity Authority no pudo revalidar el contexto AGENT"
            ) from exc
