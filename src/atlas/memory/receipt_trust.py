"""Fail-closed propagation of canonical receipt trust context to verifiers."""
from datetime import datetime

from atlas.memory.receipt_verification import (
    TerminalReceiptVerificationRequest,
    VerifiedTerminalReceipt,
    match_verified_receipt,
)
from atlas.memory.trust import ReceiptTrustContext


def _valid_time(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
        and value.utcoffset().total_seconds() == 0
    )


def verify_terminal_receipt_with_context(
    verifier: object,
    context_factory: object,
    request: TerminalReceiptVerificationRequest,
    *,
    purpose: str,
    verification_time: datetime,
) -> VerifiedTerminalReceipt | None:
    """Build and validate context before invoking only the trust-aware port."""
    if not _valid_time(verification_time):
        return None
    factory = getattr(context_factory, "for_terminal_receipt", None)
    verify = getattr(verifier, "verify_terminal_receipt_with_context", None)
    if not callable(factory) or not callable(verify):
        return None
    try:
        context = factory(
            request,
            purpose=purpose,
            verification_time=verification_time,
        )
        if (
            not isinstance(context, ReceiptTrustContext)
            or context.purpose != purpose
            or context.verification_time != verification_time
            or not context.binds_terminal_request(request)
        ):
            return None
        result = verify(request, context)
    except Exception:
        return None
    return match_verified_receipt(request, result)


def verify_recovery_completion_with_context(
    verifier: object,
    context_factory: object,
    request: object,
    receipt: object,
    *,
    purpose: str,
    verification_time: datetime,
):
    """Return global evidence only from an exact trust-aware verification."""
    if not _valid_time(verification_time):
        return None
    factory = getattr(context_factory, "for_recovery_completion", None)
    verify = getattr(verifier, "verify_recovery_completion_with_context", None)
    if not callable(factory) or not callable(verify):
        return None
    try:
        context = factory(
            request,
            receipt,
            purpose=purpose,
            verification_time=verification_time,
        )
        if (
            not isinstance(context, ReceiptTrustContext)
            or context.purpose != purpose
            or context.verification_time != verification_time
            or not context.binds_recovery_completion(request, receipt)
        ):
            return None
        verified = verify(request, receipt, context)
    except Exception:
        return None
    if getattr(verified, "receipt", None) != receipt:
        return None
    return verified
