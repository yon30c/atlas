"""Puerto de autorización CAM."""
from typing import Protocol

from atlas.authorization.models import (
    AuthorizationRequest,
    AuthorizationResult,
)


class AuthorizationPort(Protocol):
    def evaluate(
        self,
        request: AuthorizationRequest,
    ) -> AuthorizationResult:
        """Evalúa una operación sin ejecutarla."""