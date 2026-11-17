"""Puerto para revalidar evidencia de identidad de usuario."""

from typing import Protocol

from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext


class VerifiedIdentityContextVerifierPort(Protocol):
    """Revalida evidencia efímera contra Identity Authority."""

    def verify(
        self, context: VerifiedIdentityContext
    ) -> CanonicalUserIdentity:
        """Devuelve el par canónico vigente o falla cerrado."""
