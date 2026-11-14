# ME-03K — Checkpoint projection format and integrity manifest

Status: design frozen for codec v1; implementation committed for owner validation.
Scope: deterministic serialization and local integrity checking of a checkpoint base projection. This document does not define a trust anchor or a storage adapter.

## 1. Purpose and trust boundary

A checkpoint projection is the reducer's exact base state at a checkpoint position. It must survive process restart without losing Python domain types or changing semantic values.

The codec provides:
- a versioned canonical byte representation;
- strict reconstruction into the existing immutable domain dataclasses;
- a content commitment for the state blob;
- a separate content commitment for an integrity manifest;
- binding of both retrieved objects to the exact opaque references stored in the checkpoint.

The codec does **not** authenticate who published an object, prove that its storage is independent, prove completeness of external inventories, or prevent rollback to an older coherent copy. Those properties remain responsibilities of the configured independent projection/inventory verification ports and, later, any external Trust Anchor.

## 2. Projection document

The state object is canonical JSON v1 with this logical envelope:

```json
{
  "format": "atlas-consistency-projection",
  "format_version": 1,
  "projection": { "...": "all ConsistencyProjection dataclass fields" }
}
```

The projection payload is the complete `ConsistencyProjection` dataclass, including `replay_metadata_version`. Only replay metadata version 1 is accepted for checkpoint persistence.

Canonicalization reuses `atlas.memory.local_auth.canonical_json_bytes` and its existing canonicalization version. No second JSON canonicalizer is introduced.

### Strict decoding

The decoder reconstructs the declared dataclass graph using the current model type annotations. It preserves:
- dataclasses and nested dataclasses;
- enums by their exact declared values;
- UTC datetimes in the existing microsecond `Z` representation;
- tuples;
- frozensets, including canonical sorted representation;
- exact bool, integer and string types (bool is never accepted as int).

It rejects:
- duplicate JSON object keys;
- noncanonical JSON bytes;
- missing or unknown envelope/dataclass fields;
- unknown enum values or unsupported Python field types;
- incorrect tuple/set shapes or duplicate set members;
- non-UTC or noncanonical datetime values;
- unsupported format or replay metadata versions;
- reconstructed values that do not re-encode to the exact original bytes.

Dataclass constructor validation remains active during reconstruction.

## 3. State commitment and reference

Let `S` be the exact canonical projection document bytes.

- `state_commitment = lowercase_hex(SHA256(S))`
- `state_reference = "sha256:" + state_commitment`

The reference is content-addressed and opaque to the journal. It is not a filesystem path or URL.

## 4. Integrity manifest

The separate integrity manifest is canonical JSON v1 serialized from the immutable `CheckpointProjectionManifest` model. Its logical fields are:

| Field | Meaning |
|---|---|
| `manifest_format` | `atlas-consistency-projection-integrity` |
| `manifest_version` | Manifest format version, currently 1 |
| `projection_format` | State document format identifier |
| `projection_format_version` | State document version, currently 1 |
| `canonicalization_version` | Existing canonical JSON version |
| `checkpoint_id` | Exact checkpoint identity |
| `consistency_domain_id` | Projection domain |
| `authority_epoch` | Projection authority epoch |
| `sequence` | Projection head represented by the checkpoint |
| `state_reference` | Content-addressed reference to the state blob |
| `state_commitment` | SHA-256 commitment to the exact state bytes |
| `schema_version` | Checkpoint schema version |
| `reducer_version` | Reducer version that produced the projection |
| `trust_policy_version` | Policy version under which the projection is accepted |

Let `M` be the exact canonical manifest bytes.

- `integrity_commitment = lowercase_hex(SHA256(M))`
- `integrity_reference = "sha256:" + integrity_commitment`

The manifest binds the state digest to checkpoint identity, domain, epoch, sequence, schema, reducer and trust policy. It is a distinct integrity object, not a duplicate hash of the state.

The manifest deliberately does not contain its own `integrity_reference`, which would create a circular commitment.

## 5. Read-back verification

A reader must obtain both byte objects using the references from the checkpoint, then call the codec with those exact expected references.

The codec verifies:
1. both documents are canonical and use supported versions;
2. the state digest equals the manifest's state commitment;
3. the state reference equals the content-addressed state digest;
4. the manifest digest equals the checkpoint's expected integrity reference;
5. the state reference equals the checkpoint's expected state reference;
6. projection domain, epoch and sequence equal the manifest bindings.

The caller must additionally compare checkpoint ID, schema version, reducer version and trust-policy version with the trusted request. The existing `require_verified_checkpoint_projection()` exact-request boundary remains mandatory.

A successful codec read-back is necessary but not sufficient for `VERIFIED`. Only the configured independent projection verification adapter may issue `CheckpointProjectionResolution(VERIFIED, ...)`.

## 6. Publication order and adapter responsibilities

The future independent projection store must:
1. persist the state bytes immutably under `state_reference`;
2. persist the manifest bytes immutably under `integrity_reference`;
3. read both objects back;
4. verify exact references and bytes with this codec;
5. return opaque references to the checkpoint writer.

The SQLite writer must not begin its write transaction until publication and read-back have succeeded. Orphaned immutable objects are acceptable if the subsequent SQLite transaction fails. A checkpoint pointing to missing or unverified objects is not acceptable.

The codec itself performs no filesystem operations and makes no trust decision.

## 7. Compatibility and evolution

- Existing canonicalization v1 remains unchanged.
- Projection format v1 and manifest v1 are explicit and independently versioned.
- Unknown versions fail closed.
- This change does not alter SQLite schema v1-v3 and does not require a migration.
- Future incompatible projection changes require a new format version and explicit decoder/migration policy. Historical bytes must remain readable by their declared version; never reinterpret old bytes under new semantics.

## 8. Explicit non-claims

This format does not provide:
- external anti-rollback protection;
- detection of a coherent restoration of older state and manifest objects;
- independent custody merely because two files or directories are used;
- cryptographic publisher identity;
- cross-host consensus or distributed fencing;
- atomic commit across projection storage and SQLite.

Those are separate storage, trust-policy and Trust Anchor concerns.
