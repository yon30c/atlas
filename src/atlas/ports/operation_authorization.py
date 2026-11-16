"""Puerto CAM para evaluar autorización de operaciones generales."""
from datetime import datetime
from typing import Protocol

from atlas.authorization.models import AuthorizationRequest
from atlas.authorization.operation_models import OperationAuthorizationResult


class OperationAuthorizationPort(Protocol):
    def authorize_operation(
        self,
        request: AuthorizationRequest,
        now: datetime,
    ) -> OperationAuthorizationResult:
        """Evalúa una operación exacta sin ejecutarla."""
