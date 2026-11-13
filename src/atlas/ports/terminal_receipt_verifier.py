"""Port for independent verification of terminal consistency receipts."""
from typing import Protocol

from atlas.memory.receipt_verification import (
    ReceiptVerificationResult,
    TerminalReceiptVerificationRequest,
)


class TerminalReceiptVerifierPort(Protocol):
    """Trust boundary backed by configured issuer trust, not journal assertions.

    Implementations resolve trusted issuers and validate authenticity, domain/
    epoch binding, exact operation/admission/endpoint/generation/sequence,
    terminal outcome, expiry and replay. The request never supplies a trusted
    issuer identity. Exceptions or unknown outcomes must be treated as
    UNAVAILABLE by callers.
    """

    def verify_terminal_receipt(
        self,
        request: TerminalReceiptVerificationRequest,
    ) -> ReceiptVerificationResult:
        """Return VERIFIED only after independent trust and binding checks."""
