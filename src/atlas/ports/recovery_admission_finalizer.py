"""Puerto para finalizar admisiones después de verificar todos sus fences."""

from typing import Protocol

from atlas.memory.recovery_finalization import (
    RecoveryAdmissionFinalizationRequest,
    RecoveryAdmissionTerminalReceipt,
)


class RecoveryAdmissionFinalizerPort(Protocol):
    """Autoridad que emite un recibo terminal idempotente para una admisión."""

    def finalize_cancelled_admission(
        self,
        request: RecoveryAdmissionFinalizationRequest,
    ) -> RecoveryAdmissionTerminalReceipt | None:
        """Confirma CANCELLED solo si todos los endpoints exactos están cercados.

        La implementación debe ser idempotente por (domain, epoch, operation,
        admission, generation), y devolver el mismo recibo en reintentos.
        No abre el gate del dominio ni modifica otras admisiones.
        """
