"""Puerto que emite un recibo global de recuperación tras validar todas las admisiones."""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.memory.recovery_completion import RecoveryCompletionRequest, RecoveryCompletionReceipt


class RecoveryCompletionFinalizerPort(Protocol):
    def finalize_recovery(
        self,
        request: RecoveryCompletionRequest,
    ) -> RecoveryCompletionReceipt | None:
        """Emite un recibo idempotente para el inventario exacto de recuperación."""
