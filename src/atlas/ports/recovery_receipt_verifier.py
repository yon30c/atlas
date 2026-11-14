"""Puerto independiente de verificación de finalización global."""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

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
