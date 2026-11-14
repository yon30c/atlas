"""Port for independent verification of terminal consistency receipts."""
from typing import Protocol

from atlas.memory.receipt_verification import (
    ReceiptVerificationResult,
    TerminalReceiptVerificationRequest,
)
from atlas.memory.trust import ReceiptTrustContext


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


class TrustAwareTerminalReceiptVerifierPort(TerminalReceiptVerifierPort, Protocol):
    """ME-03K trust-context-aware receipt verification contract.

    This is the required interface for durable adapters. The legacy method
    remains for existing in-process test doubles during migration only; it
    cannot be treated as satisfying ME-03K-C in production composition.
    """

    def verify_terminal_receipt_with_context(
        self,
        request: TerminalReceiptVerificationRequest,
        trust_context: "ReceiptTrustContext",
    ) -> ReceiptVerificationResult:
        """Verify only if trust_context.binds_terminal_request(request) is true.

        Resolve canonical_request_reference to the immutable canonical request,
        compare every semantic field, then validate issuer authorization, key
        status, authenticity, validity interval, revocation and replay. The
        caller-supplied context is not itself proof of authenticity.
        """
