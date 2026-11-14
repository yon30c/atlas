"""Puerto independiente de verificación de finalización global."""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

from atlas.memory.trust import ReceiptTrustContext

if TYPE_CHECKING:
    from atlas.memory.recovery_completion import (
        RecoveryCompletionReceipt,
        RecoveryCompletionRequest,
        VerifiedRecoveryCompletionReceipt,
    )


class RecoveryCompletionVerifierPort(Protocol):
    def verify_recovery_completion(
        self,
        request: RecoveryCompletionRequest,
        receipt: RecoveryCompletionReceipt,
    ) -> VerifiedRecoveryCompletionReceipt | None:
        """Valida emisor y binding exacto de dominio, época, operación e inventarios."""



class TrustAwareRecoveryCompletionVerifierPort(RecoveryCompletionVerifierPort, Protocol):
    """Required verifier boundary for durable ME-03K adapters."""

    def verify_recovery_completion_with_context(
        self,
        request: RecoveryCompletionRequest,
        receipt: RecoveryCompletionReceipt,
        trust_context: ReceiptTrustContext,
    ) -> VerifiedRecoveryCompletionReceipt | None:
        """Verify only if trust_context.binds_recovery_completion(request, receipt).

        Resolve the canonical request reference, verify the exact admission and
        route inventories plus the commitment to verified terminal receipts,
        then validate issuer authorization, key status, authenticity, validity,
        revocation and replay. The context itself is not proof of authenticity.
        """
