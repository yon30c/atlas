
"""Fixtures reutilizables para pruebas."""
from datetime import datetime, timezone

from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.identity import Identity, IdentityKind, IdentityStatus


def user_context(user_id: str = "user-1") -> OperationContext:
    actor = Identity(
        identity_id="assistant",
        kind=IdentityKind.AGENT,
        status=IdentityStatus.ACTIVE,
    )

    return OperationContext(
        request_id="test-request",
        correlation_id="test-correlation",
        actor=actor,
        user_id=user_id,
        origin="unit-test",
        delegation=DelegationMode.DELEGATED,
        project_id="atlas",
        environment="development",
        purpose="unit test",
        classification="internal",
        created_at=datetime.now(timezone.utc),
    )
