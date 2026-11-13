"""Fail-closed verification of terminal admission projections."""
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    EndpointProjectionStatus,
)
from atlas.memory.consistency import ReadAdmissionStatus
from atlas.memory.receipt_verification import (
    ReceiptVerificationStatus,
    TerminalReceiptKind,
    TerminalReceiptVerificationRequest,
    VerifiedAdmissionTerminalEvidence,
    match_verified_receipt,
)


def verify_terminal_admission_projection(
    admission: AdmissionProjection,
    consistency_domain_id: str,
    authority_epoch: int,
    verifier: object,
) -> VerifiedAdmissionTerminalEvidence | None:
    """Verify every endpoint and admission receipt; never trusts receipt IDs alone.

    This returns evidence about terminal metadata only. It does not reconstruct
    an active admission, authorize a read, or create a content-delivery capability.
    """
    if not isinstance(admission, AdmissionProjection) or not admission.recoverable:
        return None
    if admission.status not in (
        ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED
    ):
        return None
    if (
        not isinstance(consistency_domain_id, str)
        or not consistency_domain_id.strip()
        or isinstance(authority_epoch, bool)
        or not isinstance(authority_epoch, int)
        or authority_epoch < 1
        or not callable(getattr(verifier, "verify_terminal_receipt", None))
    ):
        return None
    if (
        not admission.route_ids
        or {endpoint.endpoint_id for endpoint in admission.endpoints} != admission.route_ids
        or len(admission.endpoints) != len(admission.route_ids)
        or admission.terminal_receipt_id is None
        or admission.terminal_operation_id is None
        or admission.terminal_generation != admission.generation
    ):
        return None

    endpoint_receipts = []
    endpoint_statuses = set()
    for endpoint in admission.endpoints:
        if (
            endpoint.status is EndpointProjectionStatus.OPEN
            or endpoint.terminal_receipt_id is None
            or endpoint.terminal_operation_id is None
            or endpoint.terminal_generation is None
        ):
            return None
        if endpoint.status is EndpointProjectionStatus.COMPLETED:
            if (
                endpoint.final_sequence is None
                or endpoint.final_sequence < endpoint.last_emission_sequence
            ):
                return None
            kind = TerminalReceiptKind.ENDPOINT_COMPLETED
            previous_generation = None
            final_sequence = endpoint.final_sequence
        elif endpoint.status is EndpointProjectionStatus.FENCED:
            if (
                endpoint.final_sequence is not None
                or endpoint.terminal_generation <= admission.generation
            ):
                return None
            kind = TerminalReceiptKind.ENDPOINT_FENCED
            previous_generation = admission.generation
            final_sequence = None
        else:
            return None
        request = TerminalReceiptVerificationRequest(
            consistency_domain_id=consistency_domain_id,
            authority_epoch=authority_epoch,
            operation_id=endpoint.terminal_operation_id,
            admission_id=admission.admission_id,
            receipt_id=endpoint.terminal_receipt_id,
            kind=kind,
            generation=endpoint.terminal_generation,
            endpoint_id=endpoint.endpoint_id,
            previous_generation=previous_generation,
            final_sequence=final_sequence,
        )
        try:
            result = verifier.verify_terminal_receipt(request)
        except Exception:
            return None
        verified = match_verified_receipt(request, result)
        if verified is None:
            return None
        endpoint_receipts.append(verified)
        endpoint_statuses.add(endpoint.status)

    if admission.status is ReadAdmissionStatus.COMPLETED:
        if endpoint_statuses != {EndpointProjectionStatus.COMPLETED}:
            return None
        admission_kind = TerminalReceiptKind.ADMISSION_COMPLETED
    else:
        if EndpointProjectionStatus.FENCED not in endpoint_statuses:
            return None
        admission_kind = TerminalReceiptKind.ADMISSION_CANCELLED

    admission_request = TerminalReceiptVerificationRequest(
        consistency_domain_id=consistency_domain_id,
        authority_epoch=authority_epoch,
        operation_id=admission.terminal_operation_id,
        admission_id=admission.admission_id,
        receipt_id=admission.terminal_receipt_id,
        kind=admission_kind,
        generation=admission.terminal_generation,
    )
    try:
        admission_result = verifier.verify_terminal_receipt(admission_request)
    except Exception:
        return None
    verified_admission_receipt = match_verified_receipt(
        admission_request, admission_result
    )
    if verified_admission_receipt is None:
        return None
    return VerifiedAdmissionTerminalEvidence(
        admission_id=admission.admission_id,
        terminal_status=admission.status,
        endpoint_receipts=tuple(endpoint_receipts),
        admission_receipt=verified_admission_receipt,
    )
