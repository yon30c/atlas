"""Test-only trusted identity evidence fixture for owner-operation tests."""

from datetime import datetime, timedelta, timezone

from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
OWNER_USER_ID = "a6b2b66f-7c72-4d77-8d84-7d0a8c5a1001"
OWNER_IDENTITY_ID = "b6b2b66f-7c72-4d77-8d84-7d0a8c5a1002"
VERIFIED_OWNER = VerifiedIdentityContext(
    context_id="c6b2b66f-7c72-4d77-8d84-7d0a8c5a1003",
    identity_id=OWNER_IDENTITY_ID,
    identity_type=IdentityKind.USER,
    identity_revision=1,
    user_id=OWNER_USER_ID,
    binding_id="d6b2b66f-7c72-4d77-8d84-7d0a8c5a1004",
    binding_revision=1,
    issuer_id="e6b2b66f-7c72-4d77-8d84-7d0a8c5a1005",
    authenticated_at=NOW - timedelta(seconds=1),
    verified_at=NOW,
    expires_at=NOW + timedelta(minutes=5),
    verification_ref="A" * 43,
    attestation="B" * 43,
)


class FakeVerifiedIdentityContextVerifier:
    """Explicit test double; production composition must use Identity Authority."""

    def __init__(self):
        self.verify_calls = 0
        self.verify_in_uow_calls = 0
        self.last_unit_of_work = None

    def verify(self, context):
        self.verify_calls += 1
        if context != VERIFIED_OWNER:
            raise ValueError("invalid test evidence")
        return self._canonical()

    def verify_in_unit_of_work(self, context, unit):
        self.verify_in_uow_calls += 1
        self.last_unit_of_work = unit
        if context != VERIFIED_OWNER:
            raise ValueError("invalid test evidence")
        return self._canonical()

    @staticmethod
    def _canonical():
        return CanonicalUserIdentity(
            user_id=OWNER_USER_ID,
            identity=Identity(
                identity_id=OWNER_IDENTITY_ID,
                kind=IdentityKind.USER,
                status=IdentityStatus.ACTIVE,
                revision=1,
            ),
        )
