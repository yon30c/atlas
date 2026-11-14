# ME-03K — SQLite durable journal read and verification contract

## Scope

The local SQLite adapter now exposes two distinct read boundaries:

- `load_recovery_state()`: structural diagnostic read only.
- `load_verified_recovery_state()`: operational local-profile read, enabled only when an explicit verifier and the exact immutable trust-policy object are injected at construction.

Neither path claims external anti-rollback protection. The implementation does not provision keys, modify systemd credentials, change services, or deploy to production.

## Structural read

`load_recovery_state_result(domain_id)` returns a typed `ConsistencyRecoveryLoadResult`:

- `LOADED`: one SQLite read transaction observed a structurally coherent state.
- `REJECTED`: malformed or internally inconsistent persisted evidence.
- `UNAVAILABLE`: domain/state absent, database access failure, empty journal, or checkpoint path not yet supported.

A loaded state is still untrusted. Structural validation requires:

- Local profile and exact configured trust-policy version.
- A non-empty journal beginning at sequence 1. Checkpoint-backed histories return UNAVAILABLE until checkpoint/projection loading is implemented.
- Journal row count and operation row count equal the persisted head.
- Exactly one operation-resolution row maps to each journal entry by domain, epoch, sequence, record ID and operation ID.
- Contiguous sequence numbers from 1 through head.
- Typed transition reconstruction and exact canonical-byte round trip.
- Duplicated record metadata agrees with the reconstructed transition.
- Typed envelope reconstruction, exact entry binding, predecessor continuity, and final commitment equal to the persisted domain head.

No partial state is returned. The compatibility method `load_recovery_state()` returns a state only for LOADED and remains diagnostic-only.

## Operational local verification

`load_verified_recovery_state(domain_id)` follows this order:

1. Require explicit `LocalConsistencyRecoveryVerifier` and `LocalConsistencyTrustPolicy` composition. They must be the same policy object, and its version must match the journal's configured policy version. No implicit default or trust downgrade exists.
2. Load a typed structural result. Preserve REJECTED and UNAVAILABLE distinctly.
3. Construct a local recovery trust context for the exact domain and epoch.
4. Invoke the existing verifier. It checks the independent policy allowlist, historical key availability, HMAC authenticity, envelope metadata and chain continuity.
5. Only after chain verification, the verifier runs the reducer and independent inventory verification.
6. Return typed VERIFIED, REJECTED or UNAVAILABLE. Only VERIFIED includes `VerifiedLocalConsistencyRecoveryState`; this explicitly states `external_anti_rollback_protected=False`.

An absent verifier configuration returns UNAVAILABLE. Unexpected verifier exceptions also return UNAVAILABLE. Invalid persisted evidence returns REJECTED. A missing or malformed historical key remains UNAVAILABLE through the existing key-verification contract.

## Deliberate exclusions

- Durable checkpoint and checkpoint-projection loading; encountering any checkpoint returns UNAVAILABLE rather than silently replaying an incomplete journal.
- Anchored-profile recovery and external Trust Anchor integration.
- Endpoint receipt loading, checkpoint commits, Recovery Gate changes, or production composition.
- Key generation, rotation, systemd credential provisioning, service changes, or production deployment.
- Protection against restoration of a coherent older database backup.

## Validation

Static implementation and test additions are committed to `feature/me-03k-local-profile`. The user must run targeted and full test suites on Debian. No tests are claimed as executed by the assistant.
