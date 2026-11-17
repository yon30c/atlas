"""Application service for native password verification and proof issuance.

This service is deliberately not an HTTP/login entrypoint. Production composition
must provide an atomic, shared AuthenticationAttemptGuard implementation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import uuid4

from atlas.authentication.credentials import LoginHandle, validate_password_for_verification
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticatorStatus,
    NativeProofReference,
)
from atlas.core.errors import AtlasError, ConcurrencyError, ContractError
from atlas.ports.authentication_attempt_guard import AuthenticationAttemptGuardPort
from atlas.ports.clock import Clock


_DUMMY_PASSWORD = "atlas-dummy-verifier-material-never-a-real-secret"


class _NativeAuthenticationUnitOfWork(Protocol):
    native_identity: object
    native_authentication: object

    def __enter__(self): ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...


class AuthenticationUnitOfWorkFactory(Protocol):
    def __call__(self) -> _NativeAuthenticationUnitOfWork: ...


class AuthenticationFailed(AtlasError):
    """Generic denial; intentionally does not reveal which credential check failed."""


class AuthenticationUnavailable(AtlasError):
    """Authentication could not be completed safely; callers must fail closed."""


@dataclass(frozen=True, slots=True)
class NativeAuthenticationConfig:
    realm: str
    audience: str
    proof_ttl: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.realm, str) or not self.realm:
            raise ContractError("realm confiable debe ser no vacío")
        if not isinstance(self.audience, str) or not self.audience:
            raise ContractError("audience confiable debe ser no vacía")
        if not isinstance(self.proof_ttl, timedelta):
            raise ContractError("proof_ttl debe ser timedelta")
        if self.proof_ttl <= timedelta(0):
            raise ContractError("proof_ttl debe ser positivo; el valor configurado es el límite máximo")


@dataclass(frozen=True, slots=True, repr=False)
class NativeAuthenticationGrant:
    """Raw proof returned once, only after its database transaction commits."""

    reference: NativeProofReference
    authenticated_at: datetime
    expires_at: datetime

    def __repr__(self) -> str:
        return "NativeAuthenticationGrant(reference=<redacted>)"


class NativeAuthenticationService:
    """Verifies native credentials and issues audience-bound one-shot proofs."""

    def __init__(
        self,
        *,
        unit_of_work_factory: AuthenticationUnitOfWorkFactory,
        password_hasher,
        attempt_guard: AuthenticationAttemptGuardPort,
        clock: Clock,
        config: NativeAuthenticationConfig,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(password_hasher, "hash_password", None)):
            raise ContractError("password_hasher no implementa hash_password")
        if not callable(getattr(password_hasher, "verify_password", None)):
            raise ContractError("password_hasher no implementa verify_password")
        if not callable(getattr(password_hasher, "needs_rehash", None)):
            raise ContractError("password_hasher no implementa needs_rehash")
        if not isinstance(config, NativeAuthenticationConfig):
            raise ContractError("config debe ser NativeAuthenticationConfig")
        for method in ("is_allowed", "record_failure", "record_success"):
            if not callable(getattr(attempt_guard, method, None)):
                raise ContractError("attempt_guard no implementa el contrato requerido")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")

        self._unit_of_work_factory = unit_of_work_factory
        self._hasher = password_hasher
        self._guard = attempt_guard
        self._clock = clock
        self._config = config
        # Generated once per process from the same configured Argon2id policy.
        # It is never persisted and is used only for unknown login handles.
        try:
            self._dummy_phc = self._hasher.hash_password(_DUMMY_PASSWORD)
        except Exception as exc:
            raise AuthenticationUnavailable("servicio de autenticación no disponible") from exc

    @staticmethod
    def _now(clock: Clock) -> datetime:
        value = clock.now()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise AuthenticationUnavailable("reloj UTC no disponible")
        return value

    def authenticate(self, login_handle: str, password: str) -> NativeAuthenticationGrant:
        """Verify credentials and return a proof reference after durable commit."""
        handle = LoginHandle(login_handle)
        validate_password_for_verification(password)
        now = self._now(self._clock)

        # Resolve only the configured realm. Neither realm nor audience is request data.
        try:
            with self._unit_of_work_factory() as unit:
                issuer = unit.native_identity.get_native_issuer(self._config.realm)
                if (
                    issuer is None
                    or getattr(issuer.status, "value", None) != "ACTIVE"
                    or getattr(issuer.profile, "value", None) != "NATIVE_AUTHORITY_PROOF"
                ):
                    raise AuthenticationFailed("autenticación no válida")

                try:
                    allowed = self._guard.is_allowed(
                        issuer.issuer_id, handle.value, at=now
                    )
                except Exception as exc:
                    raise AuthenticationUnavailable(
                        "control de intentos no disponible"
                    ) from exc
                if not allowed:
                    raise AuthenticationFailed("autenticación no válida")

                authenticator = unit.native_authentication.get_native_authenticator_by_login_handle(
                    issuer.issuer_id, handle.value
                )
                encoded_hash = (
                    self._dummy_phc
                    if authenticator is None
                    else authenticator.password_hash_phc
                )
                try:
                    password_matches = self._hasher.verify_password(encoded_hash, password)
                except Exception as exc:
                    raise AuthenticationUnavailable(
                        "verificador de contraseña no disponible"
                    ) from exc

                if (
                    authenticator is None
                    or not password_matches
                    or authenticator.status is not NativeAuthenticatorStatus.ACTIVE
                ):
                    try:
                        self._guard.record_failure(
                            issuer.issuer_id, handle.value, at=now
                        )
                    except Exception as exc:
                        raise AuthenticationUnavailable(
                            "control de intentos no disponible"
                        ) from exc
                    raise AuthenticationFailed("autenticación no válida")

                current = unit.native_authentication.get_native_authenticator(
                    authenticator.authenticator_id
                )
                if (
                    current is None
                    or current.issuer_id != issuer.issuer_id
                    or current.native_subject != authenticator.native_subject
                    or current.status is not NativeAuthenticatorStatus.ACTIVE
                    or current.credential_revision != authenticator.credential_revision
                ):
                    raise AuthenticationFailed("autenticación no válida")

                if self._hasher.needs_rehash(current.password_hash_phc):
                    try:
                        replacement_phc = self._hasher.hash_password(password)
                        current = unit.native_authentication.update_native_password_hash(
                            current.authenticator_id,
                            expected_credential_revision=current.credential_revision,
                            password_hash_phc=replacement_phc,
                        )
                    except ConcurrencyError as exc:
                        raise AuthenticationFailed("autenticación no válida") from exc
                    except Exception as exc:
                        raise AuthenticationUnavailable(
                            "actualización de credencial no disponible"
                        ) from exc

                authenticated_at = self._now(self._clock)
                expires_at = authenticated_at + self._config.proof_ttl
                reference = NativeProofReference.generate()
                proof = NativeAuthenticationProof(
                    proof_id=str(uuid4()),
                    reference_digest=reference.digest,
                    issuer_id=issuer.issuer_id,
                    native_subject=current.native_subject,
                    authenticator_id=current.authenticator_id,
                    credential_revision=current.credential_revision,
                    authenticated_at=authenticated_at,
                    expires_at=expires_at,
                    audience=self._config.audience,
                )
                try:
                    unit.native_authentication.create_native_authentication_proof(proof)
                    unit.commit()
                except Exception as exc:
                    raise AuthenticationUnavailable(
                        "no se pudo emitir la prueba de autenticación"
                    ) from exc

            # Never clear throttling state before the proof transaction commits.
            try:
                self._guard.record_success(
                    issuer.issuer_id, handle.value, at=authenticated_at
                )
            except Exception as exc:
                # The proof remains unreturned and therefore unusable by the caller.
                raise AuthenticationUnavailable(
                    "control de intentos no disponible"
                ) from exc

            return NativeAuthenticationGrant(
                reference=reference,
                authenticated_at=authenticated_at,
                expires_at=expires_at,
            )
        except (AuthenticationFailed, AuthenticationUnavailable):
            raise
        except ContractError:
            raise
        except Exception as exc:
            raise AuthenticationUnavailable(
                "servicio de autenticación no disponible"
            ) from exc
