"""Persistence port owned by the native Authentication Authority."""

from datetime import datetime
from typing import Protocol

from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticator,
    NativeProofReference,
)


class NativeAuthenticationAuthorityPort(Protocol):
    """Persists native credentials and one-shot proofs; never grants CAM access."""

    def create_native_authenticator(
        self, authenticator: NativeAuthenticator
    ) -> NativeAuthenticator: ...

    def get_native_authenticator(
        self, authenticator_id: str
    ) -> NativeAuthenticator | None: ...

    def get_native_authenticator_by_login_handle(
        self, issuer_id: str, login_handle: str
    ) -> NativeAuthenticator | None: ...

    def update_native_password_hash(
        self,
        authenticator_id: str,
        *,
        expected_credential_revision: int,
        password_hash_phc: str,
    ) -> NativeAuthenticator: ...

    def create_native_authentication_proof(
        self, proof: NativeAuthenticationProof
    ) -> NativeAuthenticationProof: ...

    def consume_native_authentication_proof(
        self,
        reference: NativeProofReference,
        *,
        expected_audience: str,
        consumed_at: datetime,
    ) -> NativeAuthenticationProof | None: ...
