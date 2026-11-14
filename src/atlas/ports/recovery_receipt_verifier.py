"""Puerto independiente de verificación de finalización global."""

from typing import Protocol

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
