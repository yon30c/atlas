"""Provider-neutral factory for exact receipt-verification trust contexts."""
from datetime import datetime
from typing import Protocol, TYPE_CHECKING

from atlas.memory.trust import ReceiptTrustContext

if TYPE_CHECKING:
    from atlas.memory.receipt_verification import TerminalReceiptVerificationRequest
    from atlas.memory.recovery_completion import (
        RecoveryCompletionReceipt,
        RecoveryCompletionRequest,
    )


class ReceiptTrustContextFactoryPort(Protocol):
    """Resolve canonical request references and supply configured trust policy.

    Implementations must resolve canonical_request_reference from the trusted
    operation record. They must not derive trust from caller assertions or from
    the receipt itself. The coordinator supplies the UTC verification instant
    and purpose; the returned context must bind every request/receipt claim.
    """

    def for_terminal_receipt(
        self,
        request: "TerminalReceiptVerificationRequest",
        *,
        purpose: str,
        verification_time: datetime,
    ) -> ReceiptTrustContext:
        ...

    def for_recovery_completion(
        self,
        request: "RecoveryCompletionRequest",
        receipt: "RecoveryCompletionReceipt",
        *,
        purpose: str,
        verification_time: datetime,
    ) -> ReceiptTrustContext:
        ...
