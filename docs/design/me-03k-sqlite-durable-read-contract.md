# ME-03K — SQLite durable journal read contract

## Scope

This increment implements only the structural diagnostic read path for the local SQLite journal. It does not authenticate records, authorize recovery, feed the reducer, load checkpoint projections, or claim external anti-rollback protection.

## Read contract

`SQLiteConsistencyJournal.load_recovery_state(domain_id)` returns a `ConsistencyRecoveryState` only when one SQLite read transaction observes a structurally coherent local domain:

- The domain exists, has the local profile, and uses the adapter's configured trust-policy version.
- The current implementation supports a journal beginning at sequence 1 without a checkpoint. If any checkpoint exists for the domain, the method returns `None` until checkpoint/projection loading is implemented.
- A non-empty journal is required. An empty domain returns `None`; it is not represented as an authenticated recovery state.
- Journal sequences are contiguous from 1 through the persisted head.
- The journal row count and operation row count both equal the persisted head.
- Persisted transition bytes reconstruct into typed `ConsistencyTransition` objects.
- Duplicated metadata columns (record ID, operation ID, record kind, schema version) agree with the reconstructed transition.
- Every envelope is reconstructed from persisted columns and its predecessor commitment matches the preceding record.
- The final envelope commitment equals the domain's persisted head commitment.

Any missing, malformed, unsupported, or inconsistent data returns `None` (diagnostic read unavailable/rejected at this structural boundary). No partially reconstructed state is returned.

## Security boundary

The returned state is structurally reconstructed, not trusted. Its envelopes have not yet been verified against historical HMAC keys or the independent `LocalConsistencyTrustPolicy`. Consumers must not pass this result directly to the operational reducer.

The operational sequence remains:

1. Load structural state.
2. Verify envelope policy, historical key availability, HMAC, metadata, and continuity.
3. Only after successful chain verification, run the existing `LocalConsistencyRecoveryVerifier` pipeline, including checkpoint projection (when supported), reducer, and inventory verification.
4. Return typed `VERIFIED`, `UNAVAILABLE`, or `REJECTED` evidence. Only `VERIFIED` evidence may authorize downstream recovery.

## Deliberate exclusions

- No checkpoint or checkpoint-projection read support in this increment.
- No integration of the SQLite adapter with `LocalConsistencyRecoveryVerifier`.
- No key provisioning, systemd credential changes, service changes, or production deployment.
- No anti-rollback claim against restoration of a coherent older database backup.

## Validation status

Static implementation and test additions only. The user must run the targeted and full test suites on Debian; no tests are claimed as executed by the assistant.
