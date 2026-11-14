# ME-03G — Terminal receipt verification boundary

**Status:** design + initial pure contract implementation.  
**Scope:** independently verify endpoint and admission terminal receipts referenced by the consistency journal.  
**Non-goals:** cryptographic algorithm, key distribution, endpoint transport, durable journal, anti-rollback, or production recovery.

## 1. Why a receipt ID is insufficient

The reducer proves that a journal transition is structurally and semantically consistent. It does not prove who issued the receipt, whether its issuer is trusted, or whether the receipt actually corresponds to a terminal endpoint state.

A non-empty `receipt_id` is only an opaque reference. It must never be treated as proof by itself.

## 2. Verification request

A typed request binds the verifier lookup to:
- consistency domain and authority epoch;
- operation and admission IDs;
- receipt ID;
- terminal receipt kind;
- endpoint ID for endpoint receipts;
- generation, and previous generation for fencing;
- final sequence for endpoint completion.

The verifier resolves the trusted issuer from its own trust configuration. The journal and request do not get to nominate a trusted issuer identity.

Receipt kinds are closed:
- `ENDPOINT_COMPLETED`;
- `ENDPOINT_FENCED`;
- `ADMISSION_COMPLETED`;
- `ADMISSION_CANCELLED`.

Endpoint completion binds final sequence. Endpoint fencing binds old and new generations and the last committed sequence through which the endpoint guarantees no further emission. Admission terminal receipts bind the final COMPLETED/CANCELLED outcome.

## 3. Verification result

The port returns one of:
- `VERIFIED`: includes a verifier-attested receipt bound to every request field, a trusted issuer ID, a unique verification ID, and UTC verification time;
- `REJECTED`: the receipt is invalid, untrusted, mismatched, replayed, expired, or contradictory;
- `UNAVAILABLE`: trust material or verification service is unavailable or outcome is unknown.

Only VERIFIED with an exact field-for-field match is accepted. REJECTED and UNAVAILABLE never permit terminal restoration. Exceptions and malformed port results are treated as UNAVAILABLE.

The verified value is an in-process trust-boundary result, not a cryptographic signature format. Only a configured verifier implementation may issue it. Python type construction is not a security boundary against hostile code in the same process.

## 4. Projection requirements

To create exact verification requests, the reducer must retain:
- endpoint terminal operation ID;
- endpoint terminal generation;
- endpoint final sequence (completion only);
- endpoint terminal kind/status;
- admission terminal operation ID and generation.

These are metadata-only. No payload, content, fragments, hashes, or bearer capabilities are stored.

## 5. Terminal admission verification

A pure recovery validator accepts a terminal admission projection only if:
1. admission status is COMPLETED or CANCELLED;
2. every configured endpoint has a terminal status and terminal receipt reference;
3. each endpoint receipt independently verifies against domain, epoch, operation, admission, endpoint, generation and sequence/fencing binding;
4. the admission-level terminal receipt independently verifies against operation, admission, generation and terminal outcome;
5. terminal status semantics agree (COMPLETED requires every endpoint completed; CANCELLED requires at least one endpoint fenced).

A successful result is evidence that the terminal metadata may be restored. It is not a content capability and does not restore CAM authorization.

## 6. Nonterminal admissions

A nonterminal admission is not made terminal by verifying historical receipt IDs or by a timeout. Recovery must keep its gate closed, contact/fence each endpoint under a newer generation, obtain new independently verifiable fencing receipts, then journal the result. That active fencing workflow is a subsequent stage.

## 7. Fail-closed cases

- verifier absent or method missing;
- exception, timeout, unknown result;
- issuer untrusted or trust material unavailable;
- receipt ID, domain, epoch, operation, admission, endpoint, generation, sequence, or outcome mismatch;
- duplicate verification/replay;
- endpoint or admission receipt missing;
- endpoint set differs from the persisted route inventory.

All return no verified recovery object.

## 8. Acceptance tests

- G01 exact endpoint completion receipt accepted;
- G02 exact endpoint fence receipt accepted;
- G03 exact admission terminal receipt accepted;
- G04 receipt ID alone is insufficient;
- G05 wrong domain/epoch/operation/admission/endpoint rejected;
- G06 wrong generation or old/new generation rejected;
- G07 wrong final sequence rejected;
- G08 wrong terminal outcome rejected;
- G09 REJECTED/UNAVAILABLE/exception fail closed;
- G10 malformed verifier result fail closed;
- G11 missing endpoint receipt prevents terminal recovery;
- G12 missing admission receipt prevents terminal recovery;
- G13 mixed/contradictory endpoint states prevent terminal recovery;
- G14 v1/incomplete or nonterminal admission cannot be terminal-restored;
- G15 successful verification does not create a content capability or CAM authorization.

## 9. Limits

This validates a typed boundary and deterministic fake only. Trust-store design, cryptographic verification, issuer lifecycle, anti-replay persistence, endpoint liveness and durable recovery require real adapters and operational decisions that remain intentionally unselected.

## 10. Initial implementation and validation

Implemented:
- `TerminalReceiptVerificationRequest`, with closed receipt kinds and cross-field rules for endpoint completion, endpoint fencing, and admission terminal outcomes;
- `VerifiedTerminalReceipt` and `ReceiptVerificationResult`;
- exact field-for-field binding through `match_verified_receipt()`;
- `TerminalReceiptVerifierPort`, whose implementation must resolve trusted issuers from its own trust configuration;
- reducer projection of terminal operation ID, generation, and final sequence for each endpoint, plus terminal operation/generation for the admission;
- `verify_terminal_admission_projection()`, which verifies every endpoint receipt and the admission-level receipt, checks exact route coverage and status consistency, and returns metadata-only evidence;
- stricter invariants on `VerifiedAdmissionTerminalEvidence` to prevent cross-admission, duplicate, or mismatched terminal-outcome evidence.

Validation:
- 22 focused tests in `tests/unit/test_memory_terminal_receipt_verification.py`;
- projection assertions extended in `tests/unit/test_memory_journal_recovery_projection_v2.py`;
- GitHub Actions [Atlas CI #43530661316](https://github.com/yon30c/atlas/actions/runs/43530661316): Python 3.10, 3.11, 3.12 and 3.13 all successful.

The fake verifier validates the typed contract only. It does not implement cryptographic verification, trust-store management, replay protection across restarts, endpoint contact, or durable recovery. Nonterminal admissions are still not restored or fenced by this implementation.
