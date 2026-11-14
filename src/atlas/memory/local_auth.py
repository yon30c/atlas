"""Versioned canonical JSON and HMAC-SHA-256 primitives for local consistency evidence."""
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import hmac
import json
import re
from typing import Any

from atlas.core.errors import ContractError
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope

CANONICALIZATION_VERSION = 1
ENVELOPE_VERSION = 1
HMAC_ALGORITHM = "HMAC-SHA-256"
KEY_LENGTH_BYTES = 32
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DOMAIN = b"atlas-local-consistency-envelope\x00v1\x00"


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractError("datetime debe estar expresado en UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise ContractError("canonical JSON v1 no admite números decimales")
    if isinstance(value, datetime):
        return _utc_text(value)
    if isinstance(value, Enum):
        return _normalize(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _normalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ContractError("canonical JSON requiere claves de objeto string")
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8"))
    raise ContractError(f"tipo no admitido en canonical JSON: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize supported values using deterministic canonicalization v1."""
    try:
        return json.dumps(
            _normalize(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractError("no se pudo canonicalizar el objeto") from exc


def checkpoint_payload(checkpoint: Any) -> dict[str, Any]:
    """Canonical checkpoint fields, deliberately excluding the envelope."""
    return {
        "checkpoint_id": checkpoint.checkpoint_id,
        "position": checkpoint.position,
        "state_reference": checkpoint.state_reference,
        "integrity_reference": checkpoint.integrity_reference,
        "created_at": checkpoint.created_at,
    }


def journal_entry_payload(entry: Any) -> dict[str, Any]:
    """Canonical journal-entry fields, deliberately excluding the envelope."""
    return {"position": entry.position, "transition": entry.transition}


def object_commitment(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def verify_recovery_chain(state: Any, key_port: Any, trust_policy_version: str) -> bool:
    """Verify all local envelopes and predecessor links; no anti-rollback claim."""
    from atlas.memory.journal import ConsistencyRecoveryState

    if not isinstance(state, ConsistencyRecoveryState):
        return False
    if not isinstance(trust_policy_version, str) or not trust_policy_version.strip():
        return False
    records = []
    if state.checkpoint is not None:
        records.append(("checkpoint", state.checkpoint, checkpoint_payload(state.checkpoint)))
    records.extend(("journal_entry", entry, journal_entry_payload(entry)) for entry in state.entries)
    if not records:
        return False

    previous = None
    for kind, record, payload in records:
        envelope = record.envelope
        if not isinstance(envelope, AuthenticatedConsistencyEnvelope):
            return False
        if (envelope.object_kind != kind
                or envelope.consistency_domain_id != state.domain_id
                or envelope.authority_epoch != state.authority_epoch
                or envelope.trust_policy_version != trust_policy_version
                or envelope.previous_commitment != previous):
            return False
        try:
            key = key_port.load_key(envelope.key_reference)
        except Exception:
            return False
        if not isinstance(key, bytes) or not verify_envelope(envelope, payload, key):
            return False
        previous = envelope.object_commitment

    final_envelope = records[-1][1].envelope
    return (previous == state.continuity_reference
            and final_envelope.sequence == state.head_sequence)



def verify_recovery_chain_with_policy(state: Any, key_port: Any, trust_policy: Any) -> bool:
    """Verify the local chain against the independent server-configured allowlist.

    The policy is deliberately supplied by trusted composition, never restored
    from the recovery state. This adds issuer, role, key-reference, schema,
    reducer, envelope and canonicalization allowlists to cryptographic checks.
    It still makes no external anti-rollback or inventory-completeness claim.
    """
    from atlas.memory.local_trust_policy import LocalConsistencyTrustPolicy

    if not isinstance(trust_policy, LocalConsistencyTrustPolicy):
        return False
    from atlas.memory.journal import ConsistencyRecoveryState
    if not isinstance(state, ConsistencyRecoveryState):
        return False
    if (
        state.domain_id != trust_policy.consistency_domain_id
        or not trust_policy.supports_canonicalization(CANONICALIZATION_VERSION)
    ):
        return False

    records = []
    if state.checkpoint is not None:
        records.append(("checkpoint", state.checkpoint))
    records.extend(("journal_entry", entry) for entry in state.entries)

    if not records:
        return False
    for object_kind, record in records:
        envelope = record.envelope
        if (
            envelope is None
            or envelope.object_kind != object_kind
            or not trust_policy.authorizes_envelope(envelope)
        ):
            return False
    return verify_recovery_chain(state, key_port, trust_policy.policy_version)



def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_LENGTH_BYTES:
        raise ContractError("la clave HMAC local debe contener exactamente 32 bytes")


def _envelope_payload(envelope: AuthenticatedConsistencyEnvelope) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "object_kind": envelope.object_kind,
        "envelope_version": envelope.envelope_version,
        "consistency_domain_id": envelope.consistency_domain_id,
        "authority_epoch": envelope.authority_epoch,
        "sequence": envelope.sequence,
        "object_id": envelope.object_id,
        "schema_version": envelope.schema_version,
        "reducer_version": envelope.reducer_version,
        "previous_commitment": envelope.previous_commitment,
        "object_commitment": envelope.object_commitment,
        "issuer_id": envelope.issuer_id,
        "issuer_role": envelope.issuer_role,
        "key_reference": envelope.key_reference,
        "trust_policy_version": envelope.trust_policy_version,
        "issued_at": envelope.issued_at,
        "algorithm": HMAC_ALGORITHM,
    }


def authenticate_envelope(
    envelope: AuthenticatedConsistencyEnvelope, object_value: Any, key: bytes
) -> AuthenticatedConsistencyEnvelope:
    """Bind the exact canonical object and all envelope metadata to a 256-bit key."""
    if not isinstance(envelope, AuthenticatedConsistencyEnvelope):
        raise ContractError("envelope debe ser AuthenticatedConsistencyEnvelope")
    _validate_key(key)
    if envelope.envelope_version != ENVELOPE_VERSION:
        raise ContractError("versión de envelope no soportada")
    unsigned = replace(
        envelope, object_commitment=object_commitment(object_value),
        authentication_evidence="pending",
    )
    mac = hmac.new(
        key, _DOMAIN + canonical_json_bytes(_envelope_payload(unsigned)), hashlib.sha256
    ).hexdigest()
    return replace(unsigned, authentication_evidence=mac)


def verify_envelope(
    envelope: AuthenticatedConsistencyEnvelope, object_value: Any, key: bytes
) -> bool:
    """Verify object binding and HMAC in constant time; malformed evidence fails closed."""
    if not isinstance(envelope, AuthenticatedConsistencyEnvelope):
        return False
    try:
        _validate_key(key)
        if envelope.envelope_version != ENVELOPE_VERSION:
            return False
        if not _HEX_SHA256.fullmatch(envelope.authentication_evidence):
            return False
        if not hmac.compare_digest(envelope.object_commitment, object_commitment(object_value)):
            return False
        expected = authenticate_envelope(envelope, object_value, key)
        return hmac.compare_digest(
            envelope.authentication_evidence, expected.authentication_evidence
        )
    except (ContractError, TypeError, ValueError):
        return False
