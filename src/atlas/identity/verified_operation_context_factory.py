"""Trusted derivation of direct-owner OperationContext from verified USER evidence."""

from datetime import datetime, timedelta
from typing import Protocol

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.identity.verified_identity_context_service import (
    VerifiedIdentityContextService,
)
from atlas.ports.clock import Clock


class VerifiedOperationContextFactory:
    """Derives USER-only, non-delegated operation context after authority revalidation.

    This factory does not grant CAM permission and does not make legacy consumers
    safe by itself. Sensitive consumers must independently require/validate the
    verified identity evidence until the I-3 consumer reconciliation is complete.
    """

    def __init__(
        self,
        *,
        identity_context_service: VerifiedIdentityContextService,
        clock: Clock,
    ) -> None:
        if not isinstance(identity_context_service, VerifiedIdentityContextService):
            raise ContractError(
                "identity_context_service debe ser VerifiedIdentityContextService"
            )
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock no implementa now()")
        self._identity_context_service = identity_context_service
        self._clock = clock

    def create(
        self,
        verified: VerifiedIdentityContext,
        *,
        request_id: str,
        correlation_id: str,
        origin: str,
        purpose: str,
        classification: str,
    ) -> OperationContext:
        """Revalidate the USER and derive an operation with delegation disabled."""
        canonical = self._identity_context_service.verify(verified)
        created_at = self._clock.now()
        if (
            not isinstance(created_at, datetime)
            or created_at.tzinfo is None
            or created_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("created_at debe proceder de un Clock UTC")
        return OperationContext(
            request_id=request_id,
            correlation_id=correlation_id,
            actor=canonical.identity,
            user_id=canonical.user_id,
            origin=origin,
            delegation=None,
            project_id=None,
            environment=None,
            purpose=purpose,
            classification=classification,
            created_at=created_at,
        )
