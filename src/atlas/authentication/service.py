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
from atlas.ports.authentication_attempt_guard import (
    AuthenticationAttemptDenied,
    AuthenticationAttemptGuardPort,
    AuthenticationAttemptReservation,
)
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
    """Verifies credentials outside write transactions and issues one-shot proofs."""

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
        required = (
            "begin_attempt", "complete_failure",
            "complete_success", "abandon_attempt",
        )
        if any(not callable(getattr(attempt_guard, method, None)) for method in required):
            raise ContractError("attempt_guard no implementa el contrato de reservas")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")

        self._unit_of_work_factory = unit_of_work_factory
        self._hasher = password_hasher
        self._guard = attempt_guard
        self._clock = clock
        self._config = config
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

    def _abandon(self, reservation: AuthenticationAttemptReservation | None) -> None:
        if reservation is None:
            return
        try:
            self._guard.abandon_attempt(reservation)
        except Exception:
            # The reservation has a bounded 120-second TTL. Failure to release
            # it cannot authorize a proof; the guard remains fail-closed.
            pass

    def authenticate(self, login_handle: str, password: str) -> NativeAuthenticationGrant:
        """Verify credentials and return a proof only after both commits succeed."""
        handle = LoginHandle(login_handle)
        validate_password_for_verification(password)
        # Resolve only the configured issuer before reserving. No guard call or
        # Argon2id work may occur while this UoW is open.
        try:
            with self._unit_of_work_factory() as unit:
                issuer = unit.native_identity.get_native_issuer(self._config.realm)
                if (
                    issuer is None
                    or getattr(issuer.status, "value", None) != "ACTIVE"
                    or getattr(issuer.profile, "value", None) != "NATIVE_AUTHORITY_PROOF"
                ):
                    raise AuthenticationFailed("autenticación no válida")
        except (AuthenticationFailed, ContractError):
            raise
        except Exception as exc:
            raise AuthenticationUnavailable("autoridad de autenticación no disponible") from exc

        attempt_started_at = self._now(self._clock)
        try:
            reservation = self._guard.begin_attempt(
                issuer.issuer_id, handle.value, at=attempt_started_at
            )
        except AuthenticationAttemptDenied:
            raise AuthenticationFailed("autenticación no válida") from None
        except Exception as exc:
            raise AuthenticationUnavailable("control de intentos no disponible") from exc

        try:
            # Read the credential only after an atomic reservation exists.
            try:
                with self._unit_of_work_factory() as unit:
                    authenticator = (
                        unit.native_authentication.get_native_authenticator_by_login_handle(
                            issuer.issuer_id, handle.value
                        )
                    )
            except Exception as exc:
                raise AuthenticationUnavailable(
                    "autoridad de autenticación no disponible"
                ) from exc

            encoded_hash = (
                self._dummy_phc if authenticator is None
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
                    self._guard.complete_failure(
                        reservation, at=self._now(self._clock)
                    )
                    reservation = None
                except Exception as exc:
                    raise AuthenticationUnavailable(
                        "control de intentos no disponible"
                    ) from exc
                raise AuthenticationFailed("autenticación no válida")

            try:
                needs_rehash = self._hasher.needs_rehash(authenticator.password_hash_phc)
                replacement_phc = (
                    self._hasher.hash_password(password) if needs_rehash else None
                )
            except Exception as exc:
                raise AuthenticationUnavailable(
                    "verificador de contraseña no disponible"
                ) from exc

            authenticated_at = self._now(self._clock)
            expires_at = authenticated_at + self._config.proof_ttl
            reference = NativeProofReference.generate()
            proof_id = str(uuid4())

            # Re-read all mutable authority state after Argon2id. This short
            # transaction contains only CAS/hash metadata and proof persistence.
            with self._unit_of_work_factory() as unit:
                current_issuer = unit.native_identity.get_native_issuer(
                    self._config.realm
                )
                current = unit.native_authentication.get_native_authenticator(
                    authenticator.authenticator_id
                )
                if (
                    current_issuer is None
                    or current_issuer.issuer_id != issuer.issuer_id
                    or getattr(current_issuer.status, "value", None) != "ACTIVE"
                    or getattr(current_issuer.profile, "value", None) != "NATIVE_AUTHORITY_PROOF"
                    or current is None
                    or current.issuer_id != issuer.issuer_id
                    or current.native_subject != authenticator.native_subject
                    or current.login_handle != authenticator.login_handle
                    or current.status is not NativeAuthenticatorStatus.ACTIVE
                    or current.credential_revision != authenticator.credential_revision
                ):
                    raise AuthenticationFailed("autenticación no válida")

                if replacement_phc is not None:
                    try:
                        current = unit.native_authentication.update_native_password_hash(
                            current.authenticator_id,
                            expected_credential_revision=current.credential_revision,
                            password_hash_phc=replacement_phc,
                        )
                    except ConcurrencyError as exc:
                        raise AuthenticationFailed("autenticación no válida") from exc

                proof = NativeAuthenticationProof(
                    proof_id=proof_id,
                    reference_digest=reference.digest,
                    issuer_id=current_issuer.issuer_id,
                    native_subject=current.native_subject,
                    authenticator_id=current.authenticator_id,
                    credential_revision=current.credential_revision,
                    authenticated_at=authenticated_at,
                    expires_at=expires_at,
                    audience=self._config.audience,
                )
                unit.native_authentication.create_native_authentication_proof(proof)
                unit.commit()

            # Never reveal the raw proof unless both durable commits succeed.
            try:
                self._guard.complete_success(reservation, at=authenticated_at)
                reservation = None
            except Exception as exc:
                raise AuthenticationUnavailable(
                    "control de intentos no disponible"
                ) from exc

            return NativeAuthenticationGrant(
                reference=reference,
                authenticated_at=authenticated_at,
                expires_at=expires_at,
            )
        except (AuthenticationFailed, AuthenticationUnavailable, ContractError):
            raise
        except Exception as exc:
            raise AuthenticationUnavailable(
                "servicio de autenticación no disponible"
            ) from exc
        finally:
            self._abandon(reservation)
