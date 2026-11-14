"""Versioned canonical persistence codec for ME-03 checkpoint projections.

The codec provides deterministic bytes and integrity commitments. It does not
authenticate the storage location or establish an independent trust anchor.
"""
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

from atlas.core.errors import ContractError
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    ConsistencyProjection,
    ForgetProjection,
    IdempotencyProjection,
    InvalidationProjection,
    RecoveryProjection,
)
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.local_auth import CANONICALIZATION_VERSION, canonical_json_bytes


PROJECTION_FORMAT = "atlas-consistency-projection"
PROJECTION_FORMAT_VERSION = 1
PROJECTION_MANIFEST_FORMAT = "atlas-consistency-projection-integrity"
PROJECTION_MANIFEST_VERSION = 1
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class CheckpointProjectionManifest:
    """Integrity metadata bound to one immutable projection blob."""

    manifest_format: str
    manifest_version: int
    projection_format: str
    projection_format_version: int
    canonicalization_version: int
    checkpoint_id: str
    consistency_domain_id: str
    authority_epoch: int
    sequence: int
    state_reference: str
    state_commitment: str
    schema_version: int
    reducer_version: str
    trust_policy_version: str

    def __post_init__(self) -> None:
        for name in (
            "manifest_format", "projection_format", "checkpoint_id",
            "consistency_domain_id", "state_reference", "state_commitment",
            "reducer_version", "trust_policy_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{name} debe ser una cadena no vacía")
        validate_atlas_id(self.checkpoint_id, "checkpoint_id")
        for name in (
            "manifest_version", "projection_format_version",
            "canonicalization_version",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractError(f"{name} debe ser un entero")
        if self.manifest_format != PROJECTION_MANIFEST_FORMAT:
            raise ContractError("formato de manifiesto no admitido")
        if self.manifest_version != PROJECTION_MANIFEST_VERSION:
            raise ContractError("versión de manifiesto no admitida")
        if self.projection_format != PROJECTION_FORMAT:
            raise ContractError("formato de proyección no admitido")
        if self.projection_format_version != PROJECTION_FORMAT_VERSION:
            raise ContractError("versión de proyección no admitida")
        if self.canonicalization_version != CANONICALIZATION_VERSION:
            raise ContractError("versión de canonicalización no admitida")
        for name in ("authority_epoch", "schema_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{name} debe ser un entero positivo")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractError("sequence debe ser un entero no negativo")
        if len(self.state_commitment) != 64 or any(c not in "0123456789abcdef" for c in self.state_commitment):
            raise ContractError("state_commitment debe ser SHA-256 hexadecimal")


@dataclass(frozen=True, slots=True)
class CheckpointProjectionArtifacts:
    """Immutable bytes and content-addressed references ready for publication."""

    state_bytes: bytes
    manifest_bytes: bytes
    state_reference: str
    integrity_reference: str
    state_commitment: str
    integrity_commitment: str
    manifest: CheckpointProjectionManifest


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_constant(value: str) -> None:
    raise ContractError(f"constante JSON no permitida: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"clave JSON duplicada: {key}")
        result[key] = value
    return result


def _load_canonical_object(raw: bytes) -> Any:
    if not isinstance(raw, bytes):
        raise ContractError("el documento debe ser bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ContractError("documento JSON inválido") from exc
    if canonical_json_bytes(value) != raw:
        raise ContractError("el documento JSON no está en forma canónica")
    return value


def _decode_value(value: Any, expected_type: Any, path: str) -> Any:
    if expected_type is Any:
        raise ContractError(f"tipo Any no permitido en {path}")

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        errors = []
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return _decode_value(value, candidate, path)
            except ContractError as exc:
                errors.append(str(exc))
        raise ContractError(f"valor no coincide con ningún tipo permitido en {path}")

    if expected_type is datetime:
        if not isinstance(value, str):
            raise ContractError(f"{path} debe ser datetime")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError(f"{path} contiene datetime inválido") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ContractError(f"{path} debe estar expresado en UTC")
        if parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") != value:
            raise ContractError(f"{path} no usa la representación UTC canónica")
        return parsed

    if isinstance(expected_type, type) and issubclass(expected_type, Enum):
        if not isinstance(value, str):
            raise ContractError(f"{path} debe contener un valor enum string")
        try:
            return expected_type(value)
        except ValueError as exc:
            raise ContractError(f"{path} contiene un enum desconocido") from exc

    if isinstance(expected_type, type) and is_dataclass(expected_type):
        if not isinstance(value, dict):
            raise ContractError(f"{path} debe ser un objeto")
        hints = get_type_hints(expected_type)
        declared = {field.name for field in fields(expected_type)}
        if set(value) != declared:
            raise ContractError(f"{path} tiene campos ausentes o desconocidos")
        decoded = {
            field.name: _decode_value(value[field.name], hints[field.name], f"{path}.{field.name}")
            for field in fields(expected_type)
        }
        try:
            return expected_type(**decoded)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"{path} no satisface el modelo de dominio") from exc

    if origin is tuple:
        if not isinstance(value, list):
            raise ContractError(f"{path} debe ser una lista JSON para tuple")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(item, args[0], f"{path}[{index}]") for index, item in enumerate(value))
        if len(value) != len(args):
            raise ContractError(f"{path} tiene longitud tuple incorrecta")
        return tuple(_decode_value(item, item_type, f"{path}[{index}]") for index, (item, item_type) in enumerate(zip(value, args)))

    if origin is frozenset:
        if not isinstance(value, list):
            raise ContractError(f"{path} debe ser una lista JSON para frozenset")
        decoded = [_decode_value(item, args[0], f"{path}[]") for item in value]
        try:
            result = frozenset(decoded)
        except TypeError as exc:
            raise ContractError(f"{path} contiene elementos no hashables") from exc
        if len(result) != len(decoded):
            raise ContractError(f"{path} contiene elementos duplicados")
        return result

    if expected_type is bool:
        if not isinstance(value, bool):
            raise ContractError(f"{path} debe ser bool")
        return value
    if expected_type is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(f"{path} debe ser int")
        return value
    if expected_type is str:
        if not isinstance(value, str):
            raise ContractError(f"{path} debe ser string")
        return value

    raise ContractError(f"tipo de campo no admitido en {path}: {expected_type!r}")


def _validate_projection_shape(projection: ConsistencyProjection) -> None:
    if not isinstance(projection, ConsistencyProjection):
        raise ContractError("projection debe ser ConsistencyProjection")
    if not isinstance(projection.domain_id, str) or not projection.domain_id.strip():
        raise ContractError("domain_id debe ser una cadena no vacía")
    if (
        isinstance(projection.authority_epoch, bool)
        or not isinstance(projection.authority_epoch, int)
        or projection.authority_epoch < 1
    ):
        raise ContractError("authority_epoch debe ser un entero positivo")
    if (
        isinstance(projection.head_sequence, bool)
        or not isinstance(projection.head_sequence, int)
        or projection.head_sequence < 0
    ):
        raise ContractError("head_sequence debe ser un entero no negativo")
    if (
        isinstance(projection.replay_metadata_version, bool)
        or not isinstance(projection.replay_metadata_version, int)
        or projection.replay_metadata_version != 1
    ):
        raise ContractError("solo se pueden persistir proyecciones replay metadata v1")
    tuple_fields = (
        ("admissions", AdmissionProjection),
        ("forget_closures", ForgetProjection),
        ("invalidations", InvalidationProjection),
        ("idempotency_records", IdempotencyProjection),
        ("recovery_closures", RecoveryProjection),
    )
    for field, expected_type in tuple_fields:
        values = getattr(projection, field)
        if not isinstance(values, tuple) or any(
            not isinstance(item, expected_type) for item in values
        ):
            raise ContractError(f"{field} de proyección no es válido")
    for field in ("receipt_ids", "emission_ids"):
        values = getattr(projection, field)
        if (
            not isinstance(values, frozenset)
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise ContractError(f"{field} debe ser frozenset de cadenas no vacías")


def encode_projection(projection: ConsistencyProjection) -> bytes:
    """Encode a projection using the frozen format and canonical JSON v1."""
    _validate_projection_shape(projection)
    return canonical_json_bytes({
        "format": PROJECTION_FORMAT,
        "format_version": PROJECTION_FORMAT_VERSION,
        "projection": projection,
    })


def decode_projection(raw: bytes) -> ConsistencyProjection:
    """Decode strictly; reject noncanonical bytes, unknown fields and type drift."""
    document = _load_canonical_object(raw)
    if not isinstance(document, dict) or set(document) != {"format", "format_version", "projection"}:
        raise ContractError("envoltura de proyección inválida")
    if document["format"] != PROJECTION_FORMAT or document["format_version"] != PROJECTION_FORMAT_VERSION:
        raise ContractError("formato o versión de proyección no admitidos")
    projection = _decode_value(document["projection"], ConsistencyProjection, "projection")
    _validate_projection_shape(projection)
    if encode_projection(projection) != raw:
        raise ContractError("la proyección reconstruida no conserva sus bytes canónicos")
    return projection


def encode_manifest(manifest: CheckpointProjectionManifest) -> bytes:
    if not isinstance(manifest, CheckpointProjectionManifest):
        raise ContractError("manifest debe ser CheckpointProjectionManifest")
    return canonical_json_bytes(manifest)


def decode_manifest(raw: bytes) -> CheckpointProjectionManifest:
    document = _load_canonical_object(raw)
    manifest = _decode_value(document, CheckpointProjectionManifest, "manifest")
    if encode_manifest(manifest) != raw:
        raise ContractError("el manifiesto reconstruido no conserva sus bytes canónicos")
    return manifest


def build_checkpoint_projection_artifacts(
    projection: ConsistencyProjection,
    *,
    checkpoint_id: str,
    schema_version: int,
    reducer_version: str,
    trust_policy_version: str,
) -> CheckpointProjectionArtifacts:
    """Build content-addressed state and a separately committed integrity manifest."""
    state_bytes = encode_projection(projection)
    state_commitment = _sha256(state_bytes)
    state_reference = _SHA256_PREFIX + state_commitment
    manifest = CheckpointProjectionManifest(
        manifest_format=PROJECTION_MANIFEST_FORMAT,
        manifest_version=PROJECTION_MANIFEST_VERSION,
        projection_format=PROJECTION_FORMAT,
        projection_format_version=PROJECTION_FORMAT_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        checkpoint_id=checkpoint_id,
        consistency_domain_id=projection.domain_id,
        authority_epoch=projection.authority_epoch,
        sequence=projection.head_sequence,
        state_reference=state_reference,
        state_commitment=state_commitment,
        schema_version=schema_version,
        reducer_version=reducer_version,
        trust_policy_version=trust_policy_version,
    )
    manifest_bytes = encode_manifest(manifest)
    integrity_commitment = _sha256(manifest_bytes)
    integrity_reference = _SHA256_PREFIX + integrity_commitment
    return CheckpointProjectionArtifacts(
        state_bytes=state_bytes,
        manifest_bytes=manifest_bytes,
        state_reference=state_reference,
        integrity_reference=integrity_reference,
        state_commitment=state_commitment,
        integrity_commitment=integrity_commitment,
        manifest=manifest,
    )


def decode_checkpoint_projection_artifacts(
    state_bytes: bytes,
    manifest_bytes: bytes,
    *,
    expected_state_reference: str,
    expected_integrity_reference: str,
) -> tuple[ConsistencyProjection, CheckpointProjectionManifest, str]:
    """Verify bytes against the exact opaque references supplied by the checkpoint."""
    for name, value in (
        ("expected_state_reference", expected_state_reference),
        ("expected_integrity_reference", expected_integrity_reference),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{name} debe ser una referencia no vacía")
    projection = decode_projection(state_bytes)
    manifest = decode_manifest(manifest_bytes)
    state_commitment = _sha256(state_bytes)
    integrity_commitment = _sha256(manifest_bytes)
    if (
        manifest.state_commitment != state_commitment
        or manifest.state_reference != _SHA256_PREFIX + state_commitment
        or expected_state_reference != manifest.state_reference
        or expected_integrity_reference != _SHA256_PREFIX + integrity_commitment
        or projection.domain_id != manifest.consistency_domain_id
        or projection.authority_epoch != manifest.authority_epoch
        or projection.head_sequence != manifest.sequence
    ):
        raise ContractError("proyección, manifiesto y referencias no coinciden")
    return projection, manifest, integrity_commitment
