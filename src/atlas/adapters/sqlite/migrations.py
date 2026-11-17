"""Initial durable schema for the local consistency authority.

The migration stores control metadata and opaque canonical records only. It
intentionally has no memory-content, embedding, snippet, or content-hash table.
"""
from atlas.adapters.sqlite.database import SQLiteMigration


CORE_SCHEMA_V1 = SQLiteMigration(
    version=1,
    name="local_consistency_core",
    sql="""
    CREATE TABLE consistency_domains (
        domain_id TEXT PRIMARY KEY CHECK (length(trim(domain_id)) > 0),
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        head_sequence INTEGER NOT NULL DEFAULT 0 CHECK (head_sequence >= 0),
        head_commitment TEXT,
        profile TEXT NOT NULL CHECK (profile = 'local'),
        trust_policy_version TEXT NOT NULL CHECK (length(trim(trust_policy_version)) > 0),
        recovery_gate_state TEXT NOT NULL DEFAULT 'closed'
            CHECK (recovery_gate_state IN ('closed', 'open')),
        active_recovery_operation_id TEXT,
        active_recovery_generation INTEGER
            CHECK (active_recovery_generation IS NULL OR active_recovery_generation > 0),
        recovery_receipt_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (
            (active_recovery_operation_id IS NULL AND active_recovery_generation IS NULL)
            OR
            (active_recovery_operation_id IS NOT NULL AND active_recovery_generation IS NOT NULL)
        )
    );

    CREATE TABLE journal_entries (
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        record_id TEXT NOT NULL CHECK (length(trim(record_id)) > 0),
        operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
        record_kind TEXT NOT NULL CHECK (length(trim(record_kind)) > 0),
        schema_version INTEGER NOT NULL CHECK (schema_version > 0),
        transition_canonical BLOB NOT NULL CHECK (length(transition_canonical) > 0),
        envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
        reducer_version TEXT NOT NULL CHECK (length(trim(reducer_version)) > 0),
        previous_commitment TEXT,
        object_commitment TEXT NOT NULL CHECK (length(trim(object_commitment)) > 0),
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        issuer_role TEXT NOT NULL CHECK (length(trim(issuer_role)) > 0),
        key_reference TEXT NOT NULL CHECK (length(trim(key_reference)) > 0),
        trust_policy_version TEXT NOT NULL CHECK (length(trim(trust_policy_version)) > 0),
        issued_at TEXT NOT NULL,
        authentication_evidence TEXT NOT NULL CHECK (length(trim(authentication_evidence)) > 0),
        PRIMARY KEY (domain_id, authority_epoch, sequence),
        UNIQUE (domain_id, record_id),
        UNIQUE (domain_id, authority_epoch, operation_id),
        UNIQUE (domain_id, authority_epoch, sequence, record_id),
        FOREIGN KEY (domain_id) REFERENCES consistency_domains(domain_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE journal_operations (
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
        idempotency_key TEXT,
        request_canonical BLOB NOT NULL CHECK (length(request_canonical) > 0),
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        record_id TEXT NOT NULL CHECK (length(trim(record_id)) > 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY (domain_id, authority_epoch, operation_id),
        FOREIGN KEY (domain_id, authority_epoch, sequence, record_id)
            REFERENCES journal_entries(domain_id, authority_epoch, sequence, record_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE UNIQUE INDEX journal_operations_idempotency_unique
        ON journal_operations(domain_id, authority_epoch, idempotency_key)
        WHERE idempotency_key IS NOT NULL;

    CREATE TABLE checkpoints (
        checkpoint_id TEXT PRIMARY KEY CHECK (length(trim(checkpoint_id)) > 0),
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        sequence INTEGER NOT NULL CHECK (sequence >= 0),
        state_reference TEXT NOT NULL CHECK (length(trim(state_reference)) > 0),
        integrity_reference TEXT NOT NULL CHECK (length(trim(integrity_reference)) > 0),
        created_at TEXT NOT NULL,
        envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
        schema_version INTEGER NOT NULL CHECK (schema_version > 0),
        reducer_version TEXT NOT NULL CHECK (length(trim(reducer_version)) > 0),
        previous_commitment TEXT,
        object_commitment TEXT NOT NULL CHECK (length(trim(object_commitment)) > 0),
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        issuer_role TEXT NOT NULL CHECK (length(trim(issuer_role)) > 0),
        key_reference TEXT NOT NULL CHECK (length(trim(key_reference)) > 0),
        trust_policy_version TEXT NOT NULL CHECK (length(trim(trust_policy_version)) > 0),
        issued_at TEXT NOT NULL,
        authentication_evidence TEXT NOT NULL CHECK (length(trim(authentication_evidence)) > 0),
        UNIQUE (domain_id, authority_epoch, sequence),
        FOREIGN KEY (domain_id) REFERENCES consistency_domains(domain_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE checkpoint_projections (
        checkpoint_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL CHECK (schema_version > 0),
        reducer_version TEXT NOT NULL CHECK (length(trim(reducer_version)) > 0),
        trust_policy_version TEXT NOT NULL CHECK (length(trim(trust_policy_version)) > 0),
        state_commitment TEXT NOT NULL CHECK (length(trim(state_commitment)) > 0),
        integrity_commitment TEXT NOT NULL CHECK (length(trim(integrity_commitment)) > 0),
        projection_canonical BLOB NOT NULL CHECK (length(projection_canonical) > 0),
        verification_id TEXT NOT NULL CHECK (length(trim(verification_id)) > 0),
        created_at TEXT NOT NULL,
        FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX journal_entries_domain_position
        ON journal_entries(domain_id, authority_epoch, sequence);

    CREATE INDEX checkpoints_domain_position
        ON checkpoints(domain_id, authority_epoch, sequence);
    """,
)


# The v2 migration adds operation_id to the exact journal commit foreign key.
# A unique parent index supplies SQLite's required composite candidate key;
# rebuilding only the child table keeps journal_entries and all v1 evidence intact.
CORE_SCHEMA_V2 = SQLiteMigration(
    version=2,
    name="journal_operation_exact_commit",
    sql="""
    CREATE UNIQUE INDEX journal_entries_operation_commit_unique
        ON journal_entries(
            domain_id, authority_epoch, sequence, record_id, operation_id
        );

    CREATE TABLE journal_operations_v2 (
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
        idempotency_key TEXT,
        request_canonical BLOB NOT NULL CHECK (length(request_canonical) > 0),
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        record_id TEXT NOT NULL CHECK (length(trim(record_id)) > 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY (domain_id, authority_epoch, operation_id),
        FOREIGN KEY (
            domain_id, authority_epoch, sequence, record_id, operation_id
        )
        REFERENCES journal_entries(
            domain_id, authority_epoch, sequence, record_id, operation_id
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    INSERT INTO journal_operations_v2 (
        domain_id, authority_epoch, operation_id, idempotency_key,
        request_canonical, request_digest, sequence, record_id, created_at
    )
    SELECT
        domain_id, authority_epoch, operation_id, idempotency_key,
        request_canonical, request_digest, sequence, record_id, created_at
    FROM journal_operations;

    DROP INDEX journal_operations_idempotency_unique;
    DROP TABLE journal_operations;
    ALTER TABLE journal_operations_v2 RENAME TO journal_operations;

    CREATE UNIQUE INDEX journal_operations_idempotency_unique
        ON journal_operations(domain_id, authority_epoch, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
    """,
)




# v3 separates business-operation correlation from append identity. Each journal
# transition keeps operation_id as a non-unique correlation field; append_id is
# the unique locator for one attempted append. Legacy v2 rows receive a stable,
# collision-free deterministic append_id derived from their former primary key.
CORE_SCHEMA_V3 = SQLiteMigration(
    version=3,
    name="journal_append_identity",
    sql="""
    PRAGMA defer_foreign_keys = ON;

    CREATE TABLE journal_entries_v3 (
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        record_id TEXT NOT NULL CHECK (length(trim(record_id)) > 0),
        operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
        record_kind TEXT NOT NULL CHECK (length(trim(record_kind)) > 0),
        schema_version INTEGER NOT NULL CHECK (schema_version > 0),
        transition_canonical BLOB NOT NULL CHECK (length(transition_canonical) > 0),
        envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
        reducer_version TEXT NOT NULL CHECK (length(trim(reducer_version)) > 0),
        previous_commitment TEXT,
        object_commitment TEXT NOT NULL CHECK (length(trim(object_commitment)) > 0),
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        issuer_role TEXT NOT NULL CHECK (length(trim(issuer_role)) > 0),
        key_reference TEXT NOT NULL CHECK (length(trim(key_reference)) > 0),
        trust_policy_version TEXT NOT NULL CHECK (length(trim(trust_policy_version)) > 0),
        issued_at TEXT NOT NULL,
        authentication_evidence TEXT NOT NULL CHECK (length(trim(authentication_evidence)) > 0),
        PRIMARY KEY (domain_id, authority_epoch, sequence),
        UNIQUE (domain_id, record_id),
        UNIQUE (domain_id, authority_epoch, sequence, record_id, operation_id),
        FOREIGN KEY (domain_id) REFERENCES consistency_domains(domain_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    INSERT INTO journal_entries_v3 (
        domain_id, authority_epoch, sequence, record_id, operation_id,
        record_kind, schema_version, transition_canonical, envelope_version,
        reducer_version, previous_commitment, object_commitment, issuer_id,
        issuer_role, key_reference, trust_policy_version, issued_at,
        authentication_evidence
    )
    SELECT
        domain_id, authority_epoch, sequence, record_id, operation_id,
        record_kind, schema_version, transition_canonical, envelope_version,
        reducer_version, previous_commitment, object_commitment, issuer_id,
        issuer_role, key_reference, trust_policy_version, issued_at,
        authentication_evidence
    FROM journal_entries;

    CREATE TABLE journal_operations_v3 (
        domain_id TEXT NOT NULL,
        authority_epoch INTEGER NOT NULL CHECK (authority_epoch > 0),
        append_id TEXT NOT NULL CHECK (length(trim(append_id)) > 0),
        operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
        idempotency_key TEXT,
        request_canonical BLOB NOT NULL CHECK (length(request_canonical) > 0),
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        record_id TEXT NOT NULL CHECK (length(trim(record_id)) > 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY (domain_id, authority_epoch, append_id),
        FOREIGN KEY (
            domain_id, authority_epoch, sequence, record_id, operation_id
        )
        REFERENCES journal_entries_v3(
            domain_id, authority_epoch, sequence, record_id, operation_id
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    INSERT INTO journal_operations_v3 (
        domain_id, authority_epoch, append_id, operation_id, idempotency_key,
        request_canonical, request_digest, sequence, record_id, created_at
    )
    SELECT
        domain_id,
        authority_epoch,
        'legacy-v2:' || hex(CAST(domain_id AS BLOB)) || ':' ||
            authority_epoch || ':' || hex(CAST(operation_id AS BLOB)),
        operation_id,
        idempotency_key,
        request_canonical,
        request_digest,
        sequence,
        record_id,
        created_at
    FROM journal_operations;

    DROP TABLE journal_operations;
    DROP TABLE journal_entries;
    ALTER TABLE journal_entries_v3 RENAME TO journal_entries;
    ALTER TABLE journal_operations_v3 RENAME TO journal_operations;

    CREATE UNIQUE INDEX journal_operations_idempotency_unique
        ON journal_operations(domain_id, authority_epoch, idempotency_key)
        WHERE idempotency_key IS NOT NULL;

    CREATE INDEX journal_entries_domain_position
        ON journal_entries(domain_id, authority_epoch, sequence);
    """,
)


# v4 adds a generic durable authority-change ledger. It stores control-plane
# metadata only; authority-specific source records remain behind adapters.
CORE_SCHEMA_V4 = SQLiteMigration(
    version=4,
    name="durable_authority_change_coordination",
    sql="""
    CREATE TABLE authority_change_operations (
        operation_id TEXT PRIMARY KEY CHECK (length(trim(operation_id)) > 0),
        consumer_id TEXT NOT NULL CHECK (length(trim(consumer_id)) > 0),
        authority_kind TEXT NOT NULL CHECK (
            authority_kind IN (
                'memory', 'memory_version', 'identity', 'project',
                'environment', 'grant', 'consistency'
            )
        ),
        authority_id TEXT NOT NULL CHECK (length(trim(authority_id)) > 0),
        expected_revision INTEGER NOT NULL CHECK (expected_revision > 0),
        proposed_revision INTEGER NOT NULL CHECK (proposed_revision > expected_revision),
        change_kind TEXT NOT NULL CHECK (length(trim(change_kind)) > 0),
        request_context_ref TEXT NOT NULL CHECK (length(trim(request_context_ref)) > 0),
        requested_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN (
                'REQUESTED', 'INVALIDATION_PENDING', 'SOURCE_PENDING',
                'SOURCE_CONFIRMED', 'RECONCILING', 'COMPLETED',
                'ABORTED', 'BLOCKED'
            )
        ),
        source_revision INTEGER CHECK (source_revision IS NULL OR source_revision > 0),
        invalidation_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE authority_change_idempotency (
        consumer_id TEXT NOT NULL CHECK (length(trim(consumer_id)) > 0),
        idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) > 0),
        operation_id TEXT NOT NULL UNIQUE,
        intent_digest TEXT NOT NULL CHECK (length(intent_digest) = 64),
        intent_canonical BLOB NOT NULL CHECK (length(intent_canonical) > 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY (consumer_id, idempotency_key),
        FOREIGN KEY (operation_id) REFERENCES authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX authority_change_operations_resource
        ON authority_change_operations(consumer_id, authority_kind, authority_id, status);

    CREATE TABLE authority_change_invalidations (
        invalidation_id TEXT PRIMARY KEY CHECK (length(trim(invalidation_id)) > 0),
        operation_id TEXT NOT NULL UNIQUE,
        authority_kind TEXT NOT NULL CHECK (
            authority_kind IN (
                'memory', 'memory_version', 'identity', 'project',
                'environment', 'grant', 'consistency'
            )
        ),
        authority_id TEXT NOT NULL CHECK (length(trim(authority_id)) > 0),
        previous_revision INTEGER NOT NULL CHECK (previous_revision > 0),
        new_revision INTEGER NOT NULL CHECK (new_revision > previous_revision),
        fencing_generation INTEGER NOT NULL CHECK (fencing_generation > 0),
        status TEXT NOT NULL CHECK (status IN ('CLOSED', 'RECONCILED', 'BLOCKED')),
        created_at TEXT NOT NULL,
        reconciled_at TEXT,
        FOREIGN KEY (operation_id) REFERENCES authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE authority_change_affected_admissions (
        operation_id TEXT NOT NULL,
        admission_id TEXT NOT NULL CHECK (length(trim(admission_id)) > 0),
        previous_status TEXT NOT NULL CHECK (length(trim(previous_status)) > 0),
        previous_generation INTEGER NOT NULL CHECK (previous_generation > 0),
        PRIMARY KEY (operation_id, admission_id),
        FOREIGN KEY (operation_id) REFERENCES authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE authority_change_affected_routes (
        operation_id TEXT NOT NULL,
        admission_id TEXT NOT NULL CHECK (length(trim(admission_id)) > 0),
        route_id TEXT NOT NULL CHECK (length(trim(route_id)) > 0),
        fencing_generation INTEGER NOT NULL CHECK (fencing_generation > 0),
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'FENCED', 'COMPLETED', 'BLOCKED')),
        PRIMARY KEY (operation_id, admission_id, route_id),
        FOREIGN KEY (operation_id, admission_id)
            REFERENCES authority_change_affected_admissions(operation_id, admission_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE authority_change_source_results (
        operation_id TEXT PRIMARY KEY,
        source_revision INTEGER NOT NULL CHECK (source_revision > 0),
        result_digest TEXT NOT NULL CHECK (length(result_digest) = 64),
        result_canonical BLOB NOT NULL CHECK (length(result_canonical) > 0),
        confirmed_at TEXT NOT NULL,
        FOREIGN KEY (operation_id) REFERENCES authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE authority_change_recovery_evidence (
        evidence_id TEXT PRIMARY KEY CHECK (length(trim(evidence_id)) > 0),
        operation_id TEXT NOT NULL,
        phase TEXT NOT NULL CHECK (
            phase IN ('INVALIDATION', 'SOURCE', 'RECONCILIATION', 'ABORT')
        ),
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        evidence_canonical BLOB NOT NULL CHECK (length(evidence_canonical) > 0),
        verified_at TEXT NOT NULL,
        FOREIGN KEY (operation_id) REFERENCES authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX authority_change_recovery_by_operation
        ON authority_change_recovery_evidence(operation_id, phase);
    """,
)


# v5 introduces only the canonical internal UserId <-> Identity(USER) relation.
# External issuers/bindings and PRIVATE_MEMORY_AUTHORIZATION remain out of scope.
CORE_SCHEMA_V5 = SQLiteMigration(
    version=5,
    name="canonical_user_identity",
    sql="""
    CREATE TABLE identity_records (
        identity_id TEXT PRIMARY KEY CHECK (
            length(identity_id) = 36
            AND identity_id = lower(identity_id)
            AND length(replace(identity_id, '-', '')) = 32
            AND substr(identity_id, 9, 1) = '-'
            AND substr(identity_id, 14, 1) = '-'
            AND substr(identity_id, 19, 1) = '-'
            AND substr(identity_id, 24, 1) = '-'
            AND substr(identity_id, 15, 1) = '4'
            AND substr(identity_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND identity_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_kind TEXT NOT NULL CHECK (
            identity_kind IN ('user', 'agent', 'service', 'watcher', 'system')
        ),
        identity_status TEXT NOT NULL CHECK (
            identity_status IN ('active', 'suspended', 'revoked')
        ),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0)
    );

    CREATE TABLE atlas_users (
        user_id TEXT PRIMARY KEY CHECK (
            length(user_id) = 36
            AND user_id = lower(user_id)
            AND length(replace(user_id, '-', '')) = 32
            AND substr(user_id, 9, 1) = '-'
            AND substr(user_id, 14, 1) = '-'
            AND substr(user_id, 19, 1) = '-'
            AND substr(user_id, 24, 1) = '-'
            AND substr(user_id, 15, 1) = '4'
            AND substr(user_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND user_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        FOREIGN KEY (identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TRIGGER atlas_users_require_user_identity
    BEFORE INSERT ON atlas_users
    WHEN (
        SELECT identity_kind FROM identity_records
        WHERE identity_id = NEW.identity_id
    ) IS NOT 'user'
    BEGIN
        SELECT RAISE(ABORT, 'atlas_users requires identity_kind=user');
    END;

    CREATE TRIGGER identity_records_id_and_kind_immutable
    BEFORE UPDATE OF identity_id, identity_kind ON identity_records
    WHEN NEW.identity_id != OLD.identity_id
      OR NEW.identity_kind != OLD.identity_kind
    BEGIN
        SELECT RAISE(ABORT, 'identity_id and identity_kind are immutable');
    END;

    CREATE TRIGGER identity_records_revision_step
    BEFORE UPDATE ON identity_records
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'identity revision must increase by exactly one');
    END;

    CREATE TRIGGER identity_records_revoked_terminal
    BEFORE UPDATE OF identity_status ON identity_records
    WHEN OLD.identity_status = 'revoked'
      AND NEW.identity_status != 'revoked'
    BEGIN
        SELECT RAISE(ABORT, 'revoked identity is terminal');
    END;

    CREATE TRIGGER identity_records_no_delete
    BEFORE DELETE ON identity_records
    BEGIN
        SELECT RAISE(ABORT, 'identity records are retained as tombstones');
    END;

    CREATE TRIGGER atlas_users_identifiers_immutable
    BEFORE UPDATE ON atlas_users
    BEGIN
        SELECT RAISE(ABORT, 'canonical user identifiers are immutable');
    END;

    CREATE TRIGGER atlas_users_no_delete
    BEFORE DELETE ON atlas_users
    BEGIN
        SELECT RAISE(ABORT, 'canonical user records cannot be deleted');
    END;

    CREATE INDEX identity_records_kind_status
        ON identity_records(identity_kind, identity_status);
    """,
)



# v6 rebuilds the two identity tables with reciprocal deferred foreign keys.
# A USER identity and its atlas_users row must both exist at transaction commit.
# Legacy orphan USER identities fail the copy and leave the v5 schema untouched.
CORE_SCHEMA_V6 = SQLiteMigration(
    version=6,
    name="bidirectional_user_identity_integrity",
    sql="""
    CREATE TABLE identity_records_v6 (
        identity_id TEXT PRIMARY KEY CHECK (
            length(identity_id) = 36
            AND identity_id = lower(identity_id)
            AND length(replace(identity_id, '-', '')) = 32
            AND substr(identity_id, 9, 1) = '-'
            AND substr(identity_id, 14, 1) = '-'
            AND substr(identity_id, 19, 1) = '-'
            AND substr(identity_id, 24, 1) = '-'
            AND substr(identity_id, 15, 1) = '4'
            AND substr(identity_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND identity_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_kind TEXT NOT NULL CHECK (
            identity_kind IN ('user', 'agent', 'service', 'watcher', 'system')
        ),
        identity_status TEXT NOT NULL CHECK (
            identity_status IN ('active', 'suspended', 'revoked')
        ),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
        user_id TEXT UNIQUE CHECK (
            user_id IS NULL OR (
                length(user_id) = 36
                AND user_id = lower(user_id)
                AND length(replace(user_id, '-', '')) = 32
                AND substr(user_id, 9, 1) = '-'
                AND substr(user_id, 14, 1) = '-'
                AND substr(user_id, 19, 1) = '-'
                AND substr(user_id, 24, 1) = '-'
                AND substr(user_id, 15, 1) = '4'
                AND substr(user_id, 20, 1) IN ('8', '9', 'a', 'b')
                AND user_id NOT GLOB '*[^0-9a-f-]*'
            )
        ),
        UNIQUE (identity_id, user_id),
        CHECK (
            (identity_kind = 'user' AND user_id IS NOT NULL)
            OR
            (identity_kind != 'user' AND user_id IS NULL)
        ),
        FOREIGN KEY (user_id) REFERENCES atlas_users_v6(user_id)
            ON UPDATE NO ACTION ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
    );

    CREATE TABLE atlas_users_v6 (
        user_id TEXT PRIMARY KEY CHECK (
            length(user_id) = 36
            AND user_id = lower(user_id)
            AND length(replace(user_id, '-', '')) = 32
            AND substr(user_id, 9, 1) = '-'
            AND substr(user_id, 14, 1) = '-'
            AND substr(user_id, 19, 1) = '-'
            AND substr(user_id, 24, 1) = '-'
            AND substr(user_id, 15, 1) = '4'
            AND substr(user_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND user_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        FOREIGN KEY (identity_id, user_id)
            REFERENCES identity_records_v6(identity_id, user_id)
            ON UPDATE NO ACTION ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
    );

    INSERT INTO identity_records_v6 (
        identity_id, identity_kind, identity_status, revision,
        created_at, updated_at, user_id
    )
    SELECT
        i.identity_id, i.identity_kind, i.identity_status, i.revision,
        i.created_at, i.updated_at, u.user_id
    FROM identity_records AS i
    LEFT JOIN atlas_users AS u ON u.identity_id = i.identity_id;

    INSERT INTO atlas_users_v6 (user_id, identity_id, created_at)
    SELECT user_id, identity_id, created_at
    FROM atlas_users;

    DROP TABLE atlas_users;
    DROP TABLE identity_records;

    ALTER TABLE identity_records_v6 RENAME TO identity_records;
    ALTER TABLE atlas_users_v6 RENAME TO atlas_users;

    CREATE TRIGGER identity_records_id_and_kind_immutable
    BEFORE UPDATE OF identity_id, identity_kind ON identity_records
    WHEN NEW.identity_id != OLD.identity_id
      OR NEW.identity_kind != OLD.identity_kind
    BEGIN
        SELECT RAISE(ABORT, 'identity_id and identity_kind are immutable');
    END;

    CREATE TRIGGER identity_records_revision_step
    BEFORE UPDATE ON identity_records
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'identity revision must increase by exactly one');
    END;

    CREATE TRIGGER identity_records_revoked_terminal
    BEFORE UPDATE OF identity_status ON identity_records
    WHEN OLD.identity_status = 'revoked'
      AND NEW.identity_status != 'revoked'
    BEGIN
        SELECT RAISE(ABORT, 'revoked identity is terminal');
    END;

    CREATE TRIGGER identity_records_no_delete
    BEFORE DELETE ON identity_records
    BEGIN
        SELECT RAISE(ABORT, 'identity records are retained as tombstones');
    END;

    CREATE TRIGGER identity_records_user_id_immutable
    BEFORE UPDATE OF user_id ON identity_records
    WHEN NEW.user_id != OLD.user_id
    BEGIN
        SELECT RAISE(ABORT, 'identity user_id is immutable');
    END;

    CREATE TRIGGER identity_records_no_replace
    BEFORE INSERT ON identity_records
    WHEN EXISTS (
        SELECT 1 FROM identity_records WHERE identity_id = NEW.identity_id
    ) OR (
        NEW.user_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM identity_records WHERE user_id = NEW.user_id
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'identity records cannot be replaced');
    END;

    CREATE TRIGGER atlas_users_require_user_identity
    BEFORE INSERT ON atlas_users
    WHEN (
        SELECT identity_kind FROM identity_records
        WHERE identity_id = NEW.identity_id
    ) IS NOT 'user'
    BEGIN
        SELECT RAISE(ABORT, 'atlas_users requires identity_kind=user');
    END;

    CREATE TRIGGER atlas_users_identifiers_immutable
    BEFORE UPDATE ON atlas_users
    BEGIN
        SELECT RAISE(ABORT, 'canonical user identifiers are immutable');
    END;

    CREATE TRIGGER atlas_users_no_delete
    BEFORE DELETE ON atlas_users
    BEGIN
        SELECT RAISE(ABORT, 'canonical user records cannot be deleted');
    END;

    CREATE TRIGGER atlas_users_no_replace
    BEFORE INSERT ON atlas_users
    WHEN EXISTS (
        SELECT 1 FROM atlas_users
        WHERE user_id = NEW.user_id OR identity_id = NEW.identity_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'canonical user records cannot be replaced');
    END;

    CREATE INDEX identity_records_kind_status
        ON identity_records(identity_kind, identity_status);
    """,
)


# v7 introduces the canonical local Grant source. Permission scopes are stored
# as canonical JSON in one row so each Grant revision changes atomically.
CORE_SCHEMA_V7 = SQLiteMigration(
    version=7,
    name="canonical_sqlite_grants",
    sql="""
    CREATE TABLE authorization_grants (
        grant_id TEXT PRIMARY KEY CHECK (length(trim(grant_id)) > 0),
        owner_user_id TEXT NOT NULL CHECK (length(trim(owner_user_id)) > 0),
        subject_identity_id TEXT NOT NULL CHECK (length(trim(subject_identity_id)) > 0),
        project_id TEXT NOT NULL CHECK (length(trim(project_id)) > 0),
        environment TEXT NOT NULL CHECK (length(trim(environment)) > 0),
        resource_type TEXT NOT NULL CHECK (length(trim(resource_type)) > 0),
        resource_ids_json TEXT NOT NULL CHECK (
            length(trim(resource_ids_json)) > 2
            AND json_valid(resource_ids_json)
            AND json_type(resource_ids_json) = 'array'
        ),
        actions_json TEXT NOT NULL CHECK (
            length(trim(actions_json)) > 2
            AND json_valid(actions_json)
            AND json_type(actions_json) = 'array'
        ),
        issued_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        revision INTEGER NOT NULL CHECK (revision > 0),
        CHECK (expires_at > issued_at),
        CHECK (revoked_at IS NULL OR revoked_at >= issued_at)
    );

    CREATE INDEX authorization_grants_owner
        ON authorization_grants(owner_user_id, grant_id);
    CREATE INDEX authorization_grants_subject_scope
        ON authorization_grants(
            subject_identity_id, project_id, environment, resource_type
        );

    CREATE TRIGGER authorization_grants_identity_immutable
    BEFORE UPDATE OF grant_id, owner_user_id, subject_identity_id,
                     project_id, environment, resource_type, resource_ids_json,
                     actions_json, issued_at
    ON authorization_grants
    WHEN NEW.grant_id != OLD.grant_id
      OR NEW.owner_user_id != OLD.owner_user_id
      OR NEW.subject_identity_id != OLD.subject_identity_id
      OR NEW.project_id != OLD.project_id
      OR NEW.environment != OLD.environment
      OR NEW.resource_type != OLD.resource_type
      OR NEW.resource_ids_json != OLD.resource_ids_json
      OR NEW.actions_json != OLD.actions_json
      OR NEW.issued_at != OLD.issued_at
    BEGIN
        SELECT RAISE(ABORT, 'Grant identity and authority scope are immutable');
    END;

    CREATE TRIGGER authorization_grants_revision_step
    BEFORE UPDATE ON authorization_grants
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'Grant revision must increase by exactly one');
    END;

    CREATE TRIGGER authorization_grants_revocation_terminal
    BEFORE UPDATE OF revoked_at ON authorization_grants
    WHEN OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NOT OLD.revoked_at
    BEGIN
        SELECT RAISE(ABORT, 'Grant revocation is terminal');
    END;

    CREATE TRIGGER authorization_grants_no_delete
    BEFORE DELETE ON authorization_grants
    BEGIN
        SELECT RAISE(ABORT, 'Grants are retained as authority tombstones');
    END;
    """,
)

# v8 adds durable Grant renewal requests to the same local authority database.
CORE_SCHEMA_V8 = SQLiteMigration(
    version=8,
    name="canonical_sqlite_grant_renewals",
    sql="""
    CREATE TABLE authorization_grant_renewals (
        renewal_id TEXT PRIMARY KEY CHECK (length(trim(renewal_id)) > 0),
        grant_id TEXT NOT NULL CHECK (length(trim(grant_id)) > 0),
        owner_user_id TEXT NOT NULL CHECK (length(trim(owner_user_id)) > 0),
        subject_identity_id TEXT NOT NULL CHECK (length(trim(subject_identity_id)) > 0),
        requested_by_identity_id TEXT NOT NULL CHECK (length(trim(requested_by_identity_id)) > 0),
        current_expires_at TEXT NOT NULL,
        proposed_expires_at TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
        decided_at TEXT,
        decided_by_user_id TEXT,
        version INTEGER NOT NULL CHECK (version > 0),
        CHECK (proposed_expires_at > current_expires_at),
        CHECK (
            (status = 'pending' AND decided_at IS NULL AND decided_by_user_id IS NULL)
            OR
            (status IN ('approved', 'rejected')
             AND decided_at IS NOT NULL
             AND decided_by_user_id IS NOT NULL
             AND length(trim(decided_by_user_id)) > 0)
        ),
        FOREIGN KEY (grant_id) REFERENCES authorization_grants(grant_id)
            ON UPDATE NO ACTION ON DELETE NO ACTION
    );

    CREATE INDEX authorization_grant_renewals_grant
        ON authorization_grant_renewals(grant_id, requested_at, renewal_id);
    CREATE INDEX authorization_grant_renewals_owner
        ON authorization_grant_renewals(owner_user_id, status, requested_at);

    CREATE TRIGGER authorization_grant_renewals_binding_immutable
    BEFORE UPDATE OF renewal_id, grant_id, owner_user_id, subject_identity_id,
                     requested_by_identity_id, current_expires_at,
                     proposed_expires_at, requested_at
    ON authorization_grant_renewals
    WHEN NEW.renewal_id != OLD.renewal_id
      OR NEW.grant_id != OLD.grant_id
      OR NEW.owner_user_id != OLD.owner_user_id
      OR NEW.subject_identity_id != OLD.subject_identity_id
      OR NEW.requested_by_identity_id != OLD.requested_by_identity_id
      OR NEW.current_expires_at != OLD.current_expires_at
      OR NEW.proposed_expires_at != OLD.proposed_expires_at
      OR NEW.requested_at != OLD.requested_at
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal request binding is immutable');
    END;

    CREATE TRIGGER authorization_grant_renewals_version_step
    BEFORE UPDATE ON authorization_grant_renewals
    WHEN NEW.version != OLD.version + 1
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal version must increase by exactly one');
    END;

    CREATE TRIGGER authorization_grant_renewals_decision_terminal
    BEFORE UPDATE OF status ON authorization_grant_renewals
    WHEN OLD.status != 'pending' AND NEW.status != OLD.status
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal decision is terminal');
    END;

    CREATE TRIGGER authorization_grant_renewals_decision_immutable
    BEFORE UPDATE OF decided_at, decided_by_user_id ON authorization_grant_renewals
    WHEN OLD.status != 'pending'
      AND (
          NEW.decided_at IS NOT OLD.decided_at
          OR NEW.decided_by_user_id IS NOT OLD.decided_by_user_id
      )
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal decision evidence is immutable');
    END;

    CREATE TRIGGER authorization_grant_renewals_no_delete
    BEFORE DELETE ON authorization_grant_renewals
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal requests are retained as tombstones');
    END;
    """,
)


# v9 establishes canonical, revisioned Project and Environment metadata.
CORE_SCHEMA_V9 = SQLiteMigration(
    version=9,
    name="canonical_sqlite_project_environment_authorities",
    sql="""
    CREATE TABLE atlas_projects (
        project_id TEXT PRIMARY KEY CHECK (length(trim(project_id)) > 0),
        status TEXT NOT NULL CHECK (length(trim(status)) > 0),
        revision INTEGER NOT NULL CHECK (revision > 0)
    );

    CREATE TABLE atlas_environments (
        environment_id TEXT PRIMARY KEY CHECK (length(trim(environment_id)) > 0),
        status TEXT NOT NULL CHECK (length(trim(status)) > 0),
        revision INTEGER NOT NULL CHECK (revision > 0)
    );

    CREATE TRIGGER atlas_projects_identity_immutable
    BEFORE UPDATE OF project_id ON atlas_projects
    WHEN NEW.project_id != OLD.project_id
    BEGIN
        SELECT RAISE(ABORT, 'Project identity is immutable');
    END;

    CREATE TRIGGER atlas_projects_revision_step
    BEFORE UPDATE ON atlas_projects
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'Project revision must increase by exactly one');
    END;

    CREATE TRIGGER atlas_projects_no_delete
    BEFORE DELETE ON atlas_projects
    BEGIN
        SELECT RAISE(ABORT, 'Projects are retained as authority tombstones');
    END;

    CREATE TRIGGER atlas_environments_identity_immutable
    BEFORE UPDATE OF environment_id ON atlas_environments
    WHEN NEW.environment_id != OLD.environment_id
    BEGIN
        SELECT RAISE(ABORT, 'Environment identity is immutable');
    END;

    CREATE TRIGGER atlas_environments_revision_step
    BEFORE UPDATE ON atlas_environments
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'Environment revision must increase by exactly one');
    END;

    CREATE TRIGGER atlas_environments_no_delete
    BEFORE DELETE ON atlas_environments
    BEGIN
        SELECT RAISE(ABORT, 'Environments are retained as authority tombstones');
    END;
    """,
)


# v10 stores multi-authority operation identity and its complete target set.
# It is separate from the legacy single-authority ledger to preserve its
# NOT NULL contract and historical rows without synthetic placeholder targets.
CORE_SCHEMA_V10 = SQLiteMigration(
    version=10,
    name="durable_multi_authority_change_reservations",
    sql="""
    CREATE TABLE multi_authority_change_operations (
        operation_id TEXT PRIMARY KEY CHECK (length(trim(operation_id)) > 0),
        consumer_id TEXT NOT NULL CHECK (length(trim(consumer_id)) > 0),
        action TEXT NOT NULL CHECK (length(trim(action)) > 0),
        actor_identity_id TEXT NOT NULL CHECK (length(trim(actor_identity_id)) > 0),
        owner_id TEXT NOT NULL CHECK (length(trim(owner_id)) > 0),
        project_id TEXT,
        environment_id TEXT,
        request_context_ref TEXT NOT NULL CHECK (length(trim(request_context_ref)) > 0),
        requested_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN (
                'REQUESTED', 'INVALIDATION_PENDING', 'SOURCE_PENDING',
                'SOURCE_CONFIRMED', 'RECONCILING', 'COMPLETED',
                'ABORTED', 'BLOCKED'
            )
        ),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE multi_authority_change_idempotency (
        consumer_id TEXT NOT NULL CHECK (length(trim(consumer_id)) > 0),
        idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) > 0),
        operation_id TEXT NOT NULL UNIQUE,
        intent_digest TEXT NOT NULL CHECK (length(intent_digest) = 64),
        intent_canonical BLOB NOT NULL CHECK (length(intent_canonical) > 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY (consumer_id, idempotency_key),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE multi_authority_change_targets (
        operation_id TEXT NOT NULL,
        authority_kind TEXT NOT NULL CHECK (
            authority_kind IN (
                'memory', 'memory_version', 'identity', 'project',
                'environment', 'grant', 'grant_renewal', 'consistency'
            )
        ),
        authority_id TEXT NOT NULL CHECK (length(trim(authority_id)) > 0),
        expected_revision INTEGER NOT NULL CHECK (expected_revision > 0),
        proposed_revision INTEGER NOT NULL CHECK (
            proposed_revision = expected_revision + 1
        ),
        PRIMARY KEY (operation_id, authority_kind, authority_id),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX multi_authority_change_targets_resource
        ON multi_authority_change_targets(authority_kind, authority_id);

    CREATE TRIGGER multi_authority_change_idempotency_requires_complete_targets
    BEFORE INSERT ON multi_authority_change_idempotency
    WHEN (
        SELECT COUNT(*) FROM multi_authority_change_targets
        WHERE operation_id = NEW.operation_id
    ) < 2
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority operation requires at least two targets');
    END;

    CREATE TRIGGER multi_authority_change_operation_identity_immutable
    BEFORE UPDATE OF operation_id, consumer_id, action, actor_identity_id,
                     owner_id, project_id, environment_id, request_context_ref,
                     requested_at
    ON multi_authority_change_operations
    WHEN NEW.operation_id != OLD.operation_id
      OR NEW.consumer_id != OLD.consumer_id
      OR NEW.action != OLD.action
      OR NEW.actor_identity_id != OLD.actor_identity_id
      OR NEW.owner_id != OLD.owner_id
      OR NEW.project_id IS NOT OLD.project_id
      OR NEW.environment_id IS NOT OLD.environment_id
      OR NEW.request_context_ref != OLD.request_context_ref
      OR NEW.requested_at != OLD.requested_at
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority operation identity is immutable');
    END;

    CREATE TRIGGER multi_authority_change_targets_no_late_insert
    BEFORE INSERT ON multi_authority_change_targets
    WHEN EXISTS (
        SELECT 1 FROM multi_authority_change_idempotency
        WHERE operation_id = NEW.operation_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority target set is already sealed');
    END;

    CREATE TRIGGER multi_authority_change_targets_no_update
    BEFORE UPDATE ON multi_authority_change_targets
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority targets are immutable');
    END;

    CREATE TRIGGER multi_authority_change_targets_no_delete
    BEFORE DELETE ON multi_authority_change_targets
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority targets are retained');
    END;

    CREATE TRIGGER multi_authority_change_idempotency_no_update
    BEFORE UPDATE ON multi_authority_change_idempotency
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority idempotency binding is immutable');
    END;

    CREATE TRIGGER multi_authority_change_idempotency_no_delete
    BEFORE DELETE ON multi_authority_change_idempotency
    BEGIN
        SELECT RAISE(ABORT, 'Multi-authority idempotency is retained');
    END;
    """,
)


# v11 adds exclusive resource claims for multi-authority operations. Claims are
# acquired as a complete target set under BEGIN IMMEDIATE. They are retained
# conservatively; release is intentionally unavailable until terminal
# reconciliation evidence is implemented by the consistency coordinator.
CORE_SCHEMA_V11 = SQLiteMigration(
    version=11,
    name="exclusive_multi_authority_resource_claims",
    sql="""
    CREATE TABLE multi_authority_change_claims (
        authority_kind TEXT NOT NULL CHECK (
            authority_kind IN (
                'memory', 'memory_version', 'identity', 'project',
                'environment', 'grant', 'grant_renewal', 'consistency'
            )
        ),
        authority_id TEXT NOT NULL CHECK (length(trim(authority_id)) > 0),
        operation_id TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        PRIMARY KEY (authority_kind, authority_id),
        UNIQUE (operation_id, authority_kind, authority_id),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX multi_authority_change_claims_operation
        ON multi_authority_change_claims(operation_id);

    CREATE TRIGGER multi_authority_change_claims_require_target
    BEFORE INSERT ON multi_authority_change_claims
    WHEN NOT EXISTS (
        SELECT 1
        FROM multi_authority_change_targets AS t
        JOIN multi_authority_change_operations AS o
          ON o.operation_id = t.operation_id
        WHERE t.operation_id = NEW.operation_id
          AND t.authority_kind = NEW.authority_kind
          AND t.authority_id = NEW.authority_id
          AND o.status = 'REQUESTED'
    )
    BEGIN
        SELECT RAISE(ABORT, 'claim must match a requested operation target');
    END;

    CREATE TRIGGER multi_authority_change_claims_no_update
    BEFORE UPDATE ON multi_authority_change_claims
    BEGIN
        SELECT RAISE(ABORT, 'resource claims are immutable');
    END;

    CREATE TRIGGER multi_authority_change_claims_no_delete
    BEFORE DELETE ON multi_authority_change_claims
    BEGIN
        SELECT RAISE(ABORT, 'resource claims cannot be released before reconciliation support');
    END;
    """,
)


# v12 persists the complete terminal reconciliation receipt and gates terminal
# operation status transitions on that receipt. Claims remain retained.
CORE_SCHEMA_V12 = SQLiteMigration(
    version=12,
    name="durable_multi_authority_terminal_evidence",
    sql="""
    CREATE TABLE multi_authority_change_terminal_evidence (
        operation_id TEXT PRIMARY KEY,
        evidence_id TEXT NOT NULL UNIQUE CHECK (length(trim(evidence_id)) > 0),
        outcome TEXT NOT NULL CHECK (outcome IN ('COMPLETED', 'ABORTED')),
        evidence_ref TEXT NOT NULL CHECK (length(trim(evidence_ref)) > 0),
        recorded_by TEXT NOT NULL CHECK (length(trim(recorded_by)) > 0),
        recorded_at TEXT NOT NULL,
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        evidence_canonical BLOB NOT NULL CHECK (length(evidence_canonical) > 0),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE multi_authority_change_terminal_targets (
        operation_id TEXT NOT NULL,
        authority_kind TEXT NOT NULL,
        authority_id TEXT NOT NULL,
        expected_revision INTEGER NOT NULL CHECK (expected_revision > 0),
        proposed_revision INTEGER NOT NULL CHECK (
            proposed_revision = expected_revision + 1
        ),
        observed_revision INTEGER NOT NULL CHECK (observed_revision > 0),
        PRIMARY KEY (operation_id, authority_kind, authority_id),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_terminal_evidence(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (operation_id, authority_kind, authority_id)
            REFERENCES multi_authority_change_targets(
                operation_id, authority_kind, authority_id
            )
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TRIGGER multi_terminal_evidence_requires_reconciling_claimed_operation
    BEFORE INSERT ON multi_authority_change_terminal_evidence
    WHEN NOT EXISTS (
        SELECT 1 FROM multi_authority_change_operations
        WHERE operation_id = NEW.operation_id AND status = 'RECONCILING'
    )
    OR (
        SELECT COUNT(*) FROM multi_authority_change_claims
        WHERE operation_id = NEW.operation_id
    ) != (
        SELECT COUNT(*) FROM multi_authority_change_targets
        WHERE operation_id = NEW.operation_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal evidence requires a reconciling operation with complete claims');
    END;

    CREATE TRIGGER multi_terminal_target_requires_matching_reserved_revision
    BEFORE INSERT ON multi_authority_change_terminal_targets
    WHEN NOT EXISTS (
        SELECT 1
        FROM multi_authority_change_targets AS t
        JOIN multi_authority_change_terminal_evidence AS e
          ON e.operation_id = t.operation_id
        WHERE t.operation_id = NEW.operation_id
          AND t.authority_kind = NEW.authority_kind
          AND t.authority_id = NEW.authority_id
          AND t.expected_revision = NEW.expected_revision
          AND t.proposed_revision = NEW.proposed_revision
          AND (
              (e.outcome = 'COMPLETED'
               AND NEW.observed_revision = t.proposed_revision)
              OR
              (e.outcome = 'ABORTED'
               AND NEW.observed_revision = t.expected_revision)
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal target does not match reserved revisions and outcome');
    END;

    CREATE TRIGGER multi_terminal_evidence_no_update
    BEFORE UPDATE ON multi_authority_change_terminal_evidence
    BEGIN
        SELECT RAISE(ABORT, 'terminal evidence is immutable');
    END;

    CREATE TRIGGER multi_terminal_evidence_no_delete
    BEFORE DELETE ON multi_authority_change_terminal_evidence
    BEGIN
        SELECT RAISE(ABORT, 'terminal evidence is retained');
    END;

    CREATE TRIGGER multi_terminal_targets_no_update
    BEFORE UPDATE ON multi_authority_change_terminal_targets
    BEGIN
        SELECT RAISE(ABORT, 'terminal evidence targets are immutable');
    END;

    CREATE TRIGGER multi_terminal_targets_no_delete
    BEFORE DELETE ON multi_authority_change_terminal_targets
    BEGIN
        SELECT RAISE(ABORT, 'terminal evidence targets are retained');
    END;

    CREATE TRIGGER multi_operation_terminal_status_requires_evidence
    BEFORE UPDATE OF status ON multi_authority_change_operations
    WHEN NEW.status IN ('COMPLETED', 'ABORTED')
    AND (
        OLD.status != 'RECONCILING'
        OR NOT EXISTS (
            SELECT 1
            FROM multi_authority_change_terminal_evidence AS e
            WHERE e.operation_id = NEW.operation_id
              AND e.outcome = NEW.status
        )
        OR (
            SELECT COUNT(*) FROM multi_authority_change_terminal_targets
            WHERE operation_id = NEW.operation_id
        ) != (
            SELECT COUNT(*) FROM multi_authority_change_targets
            WHERE operation_id = NEW.operation_id
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal status requires complete matching terminal evidence');
    END;

    CREATE TRIGGER multi_operation_terminal_status_is_final
    BEFORE UPDATE OF status ON multi_authority_change_operations
    WHEN OLD.status IN ('COMPLETED', 'ABORTED') AND NEW.status != OLD.status
    BEGIN
        SELECT RAISE(ABORT, 'terminal operation status is final');
    END;
    """,
)



# v13 records verified terminal claim releases while retaining an immutable audit
# receipt. Claim rows are deleted only in the same transaction as this receipt.
CORE_SCHEMA_V13 = SQLiteMigration(
    version=13,
    name="audited_terminal_multi_authority_claim_release",
    sql="""
    CREATE TABLE multi_authority_change_claim_releases (
        operation_id TEXT PRIMARY KEY,
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        released_at TEXT NOT NULL,
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_terminal_evidence(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TRIGGER multi_claim_release_requires_verified_terminal_set
    BEFORE INSERT ON multi_authority_change_claim_releases
    WHEN NOT EXISTS (
        SELECT 1
        FROM multi_authority_change_operations AS o
        JOIN multi_authority_change_terminal_evidence AS e
          ON e.operation_id = o.operation_id
        WHERE o.operation_id = NEW.operation_id
          AND o.status IN ('COMPLETED', 'ABORTED')
          AND e.outcome = o.status
          AND e.evidence_digest = NEW.evidence_digest
          AND (
              SELECT COUNT(*) FROM multi_authority_change_targets
              WHERE operation_id = o.operation_id
          ) >= 2
          AND (
              SELECT COUNT(*) FROM multi_authority_change_claims
              WHERE operation_id = o.operation_id
          ) = (
              SELECT COUNT(*) FROM multi_authority_change_targets
              WHERE operation_id = o.operation_id
          )
          AND (
              SELECT COUNT(*) FROM multi_authority_change_terminal_targets
              WHERE operation_id = o.operation_id
          ) = (
              SELECT COUNT(*) FROM multi_authority_change_targets
              WHERE operation_id = o.operation_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM multi_authority_change_targets AS t
              LEFT JOIN multi_authority_change_claims AS c
                ON c.operation_id = t.operation_id
               AND c.authority_kind = t.authority_kind
               AND c.authority_id = t.authority_id
              LEFT JOIN multi_authority_change_terminal_targets AS tt
                ON tt.operation_id = t.operation_id
               AND tt.authority_kind = t.authority_kind
               AND tt.authority_id = t.authority_id
               AND tt.expected_revision = t.expected_revision
               AND tt.proposed_revision = t.proposed_revision
              WHERE t.operation_id = o.operation_id
                AND (c.operation_id IS NULL OR tt.operation_id IS NULL)
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'claim release requires complete matching terminal evidence and claims');
    END;

    CREATE TRIGGER multi_claim_release_no_update
    BEFORE UPDATE ON multi_authority_change_claim_releases
    BEGIN
        SELECT RAISE(ABORT, 'claim release receipts are immutable');
    END;

    CREATE TRIGGER multi_claim_release_no_delete
    BEFORE DELETE ON multi_authority_change_claim_releases
    BEGIN
        SELECT RAISE(ABORT, 'claim release receipts are retained');
    END;

    DROP TRIGGER multi_authority_change_claims_no_delete;

    CREATE TRIGGER multi_authority_change_claims_no_delete
    BEFORE DELETE ON multi_authority_change_claims
    WHEN NOT EXISTS (
        SELECT 1
        FROM multi_authority_change_claim_releases AS r
        WHERE r.operation_id = OLD.operation_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'claims require a durable terminal release receipt');
    END;
    """,
)


# v14 constrains multi-authority lifecycle transitions to a strict forward graph.
# Intermediate progression requires the complete exclusive claim set; terminal
# transitions remain separately gated by the immutable reconciliation receipt.
CORE_SCHEMA_V14 = SQLiteMigration(
    version=14,
    name="constrained_multi_authority_operation_lifecycle",
    sql="""
    CREATE TRIGGER multi_authority_operation_status_forward_only
    BEFORE UPDATE OF status ON multi_authority_change_operations
    WHEN NEW.status != OLD.status
    AND NOT (
        (OLD.status = 'REQUESTED' AND NEW.status = 'INVALIDATION_PENDING')
        OR
        (OLD.status = 'INVALIDATION_PENDING' AND NEW.status = 'SOURCE_PENDING')
        OR
        (OLD.status = 'SOURCE_PENDING' AND NEW.status = 'SOURCE_CONFIRMED')
        OR
        (OLD.status = 'SOURCE_CONFIRMED' AND NEW.status = 'RECONCILING')
        OR
        (OLD.status = 'RECONCILING' AND NEW.status IN ('COMPLETED', 'ABORTED'))
    )
    BEGIN
        SELECT RAISE(ABORT, 'invalid multi-authority operation status transition');
    END;

    CREATE TRIGGER multi_authority_operation_progress_requires_complete_claims
    BEFORE UPDATE OF status ON multi_authority_change_operations
    WHEN NEW.status != OLD.status
    AND NEW.status IN (
        'INVALIDATION_PENDING', 'SOURCE_PENDING',
        'SOURCE_CONFIRMED', 'RECONCILING'
    )
    AND (
        (SELECT COUNT(*) FROM multi_authority_change_targets
         WHERE operation_id = OLD.operation_id) < 2
        OR
        (SELECT COUNT(*) FROM multi_authority_change_claims
         WHERE operation_id = OLD.operation_id)
        !=
        (SELECT COUNT(*) FROM multi_authority_change_targets
         WHERE operation_id = OLD.operation_id)
        OR EXISTS (
            SELECT 1
            FROM multi_authority_change_targets AS t
            LEFT JOIN multi_authority_change_claims AS c
              ON c.operation_id = t.operation_id
             AND c.authority_kind = t.authority_kind
             AND c.authority_id = t.authority_id
            WHERE t.operation_id = OLD.operation_id
              AND c.operation_id IS NULL
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'multi-authority progression requires the complete claim set');
    END;
    """,
)



# v15 stores immutable, revisioned issuer trust-policy snapshots. A policy
# change appends a new revision; historical policy rows are never overwritten.
CORE_SCHEMA_V15 = SQLiteMigration(
    version=15,
    name="immutable_recovery_evidence_issuer_trust_policies",
    sql="""
    CREATE TABLE recovery_evidence_issuer_trust_policies (
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        allowed_evidence_kinds_json TEXT NOT NULL
            CHECK (length(trim(allowed_evidence_kinds_json)) > 0),
        valid_from TEXT NOT NULL CHECK (length(trim(valid_from)) > 0),
        valid_until TEXT,
        max_evidence_lifetime_seconds INTEGER NOT NULL
            CHECK (max_evidence_lifetime_seconds > 0),
        PRIMARY KEY (issuer_id, policy_revision),
        CHECK (valid_until IS NULL OR valid_until > valid_from)
    );

    CREATE INDEX recovery_evidence_trust_policy_current
        ON recovery_evidence_issuer_trust_policies(issuer_id, policy_revision DESC);

    CREATE TRIGGER recovery_evidence_trust_policy_revision_sequential
    BEFORE INSERT ON recovery_evidence_issuer_trust_policies
    WHEN NEW.policy_revision != COALESCE(
        (SELECT MAX(policy_revision) + 1
         FROM recovery_evidence_issuer_trust_policies
         WHERE issuer_id = NEW.issuer_id),
        1
    )
    BEGIN
        SELECT RAISE(ABORT, 'issuer trust policy revision must increase by exactly one');
    END;

    CREATE TRIGGER recovery_evidence_trust_policy_no_update
    BEFORE UPDATE ON recovery_evidence_issuer_trust_policies
    BEGIN
        SELECT RAISE(ABORT, 'issuer trust policy history is immutable');
    END;

    CREATE TRIGGER recovery_evidence_trust_policy_no_delete
    BEFORE DELETE ON recovery_evidence_issuer_trust_policies
    BEGIN
        SELECT RAISE(ABORT, 'issuer trust policy history is retained');
    END;
    """,
)



# v16 stores the authoritative inventory of recovery-evidence issuers as
# append-only revisioned snapshots. Registration is separate from trust policy:
# an inventory entry never authenticates an issuer or grants evidence trust.
CORE_SCHEMA_V16 = SQLiteMigration(
    version=16,
    name="immutable_recovery_evidence_issuer_registry",
    sql="""
    CREATE TABLE recovery_evidence_issuer_registry (
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        registry_revision INTEGER NOT NULL CHECK (registry_revision > 0),
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        changed_at TEXT NOT NULL CHECK (length(trim(changed_at)) > 0),
        PRIMARY KEY (issuer_id, registry_revision)
    );

    CREATE INDEX recovery_evidence_issuer_registry_current
        ON recovery_evidence_issuer_registry(issuer_id, registry_revision DESC);

    CREATE TRIGGER recovery_evidence_issuer_registry_revision_sequential
    BEFORE INSERT ON recovery_evidence_issuer_registry
    WHEN NEW.registry_revision != COALESCE(
        (SELECT MAX(registry_revision) + 1
         FROM recovery_evidence_issuer_registry
         WHERE issuer_id = NEW.issuer_id),
        1
    )
    BEGIN
        SELECT RAISE(ABORT, 'issuer registry revision must increase by exactly one');
    END;

    CREATE TRIGGER recovery_evidence_issuer_registry_no_update
    BEFORE UPDATE ON recovery_evidence_issuer_registry
    BEGIN
        SELECT RAISE(ABORT, 'issuer registry history is immutable');
    END;

    CREATE TRIGGER recovery_evidence_issuer_registry_no_delete
    BEFORE DELETE ON recovery_evidence_issuer_registry
    BEGIN
        SELECT RAISE(ABORT, 'issuer registry history is retained');
    END;
    """,
)


# v17 stores one-time admission receipts bound to exact evidence, issuer
# inventory revision, operation and complete claimed target set. Admissions are
# immutable evidence records and never grant permission to perform an effect.
CORE_SCHEMA_V17 = SQLiteMigration(
    version=17,
    name="immutable_recovery_evidence_admissions",
    sql="""
    CREATE TABLE recovery_evidence_admissions (
        admission_id TEXT PRIMARY KEY CHECK (length(trim(admission_id)) > 0),
        evidence_id TEXT NOT NULL UNIQUE CHECK (length(trim(evidence_id)) > 0),
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        operation_id TEXT NOT NULL,
        issuer_id TEXT NOT NULL CHECK (length(trim(issuer_id)) > 0),
        issuer_registry_revision INTEGER NOT NULL CHECK (issuer_registry_revision > 0),
        evidence_kind TEXT NOT NULL CHECK (length(trim(evidence_kind)) > 0),
        target_count INTEGER NOT NULL CHECK (target_count >= 2),
        command_digest TEXT NOT NULL CHECK (length(command_digest) = 64),
        command_canonical BLOB NOT NULL CHECK (length(command_canonical) > 0),
        requested_at TEXT NOT NULL CHECK (length(trim(requested_at)) > 0),
        recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
        FOREIGN KEY (operation_id)
            REFERENCES multi_authority_change_operations(operation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX recovery_evidence_admissions_operation
        ON recovery_evidence_admissions(operation_id);

    CREATE TRIGGER recovery_admission_requires_current_enabled_issuer
    BEFORE INSERT ON recovery_evidence_admissions
    WHEN NOT EXISTS (
        SELECT 1 FROM recovery_evidence_issuer_registry AS r
        WHERE r.issuer_id = NEW.issuer_id
          AND r.registry_revision = NEW.issuer_registry_revision
          AND r.enabled = 1
          AND r.registry_revision = (
              SELECT MAX(latest.registry_revision)
              FROM recovery_evidence_issuer_registry AS latest
              WHERE latest.issuer_id = NEW.issuer_id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'recovery admission requires current enabled issuer revision');
    END;

    CREATE TRIGGER recovery_admission_requires_active_claimed_operation
    BEFORE INSERT ON recovery_evidence_admissions
    WHEN NOT EXISTS (
        SELECT 1 FROM multi_authority_change_operations AS o
        WHERE o.operation_id = NEW.operation_id
          AND o.status IN (
              'INVALIDATION_PENDING', 'SOURCE_PENDING',
              'SOURCE_CONFIRMED', 'RECONCILING'
          )
    )
    OR NEW.target_count != (
        SELECT COUNT(*) FROM multi_authority_change_targets
        WHERE operation_id = NEW.operation_id
    )
    OR NEW.target_count != (
        SELECT COUNT(*) FROM multi_authority_change_claims
        WHERE operation_id = NEW.operation_id
    )
    OR EXISTS (
        SELECT 1
        FROM multi_authority_change_targets AS t
        LEFT JOIN multi_authority_change_claims AS c
          ON c.operation_id = t.operation_id
         AND c.authority_kind = t.authority_kind
         AND c.authority_id = t.authority_id
        WHERE t.operation_id = NEW.operation_id
          AND c.operation_id IS NULL
    )
    BEGIN
        SELECT RAISE(ABORT, 'recovery admission requires complete active operation claims');
    END;

    CREATE TRIGGER recovery_evidence_admissions_no_update
    BEFORE UPDATE ON recovery_evidence_admissions
    BEGIN
        SELECT RAISE(ABORT, 'recovery evidence admissions are immutable');
    END;

    CREATE TRIGGER recovery_evidence_admissions_no_delete
    BEFORE DELETE ON recovery_evidence_admissions
    BEGIN
        SELECT RAISE(ABORT, 'recovery evidence admissions are retained');
    END;
    """,
)


# v18 adds explicit Project/Environment associations and canonical workspace
# ownership/scope records. No legacy associations or workspaces are synthesized.
CORE_SCHEMA_V18 = SQLiteMigration(
    version=18,
    name="canonical_project_environment_associations_and_workspaces",
    sql="""
    CREATE TABLE atlas_project_environments (
        project_id TEXT NOT NULL,
        environment_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (project_id, environment_id),
        FOREIGN KEY (project_id) REFERENCES atlas_projects(project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (environment_id) REFERENCES atlas_environments(environment_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX atlas_project_environments_by_environment
        ON atlas_project_environments(environment_id, status, project_id);

    CREATE TRIGGER atlas_project_environment_identity_immutable
    BEFORE UPDATE OF project_id, environment_id ON atlas_project_environments
    WHEN NEW.project_id != OLD.project_id OR NEW.environment_id != OLD.environment_id
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment association identity is immutable');
    END;

    CREATE TRIGGER atlas_project_environment_revision_step
    BEFORE UPDATE ON atlas_project_environments
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment association revision must increase by exactly one');
    END;

    CREATE TRIGGER atlas_project_environment_no_delete
    BEFORE DELETE ON atlas_project_environments
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment associations are retained as tombstones');
    END;

    CREATE TABLE atlas_workspaces (
        workspace_id TEXT PRIMARY KEY CHECK (length(trim(workspace_id)) > 0),
        owner_user_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        environment_id TEXT NOT NULL,
        root_ref TEXT NOT NULL CHECK (length(trim(root_ref)) > 6 AND substr(root_ref, 1, 6) = 'mount:' AND instr(root_ref, '/') = 0 AND instr(root_ref, char(92)) = 0),
        status TEXT NOT NULL CHECK (status IN ('active', 'suspended', 'disabled')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (workspace_id, owner_user_id),
        FOREIGN KEY (owner_user_id) REFERENCES atlas_users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (project_id, environment_id)
            REFERENCES atlas_project_environments(project_id, environment_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TRIGGER atlas_workspace_requires_active_project_environment
    BEFORE INSERT ON atlas_workspaces
    WHEN NOT EXISTS (
        SELECT 1 FROM atlas_project_environments
        WHERE project_id = NEW.project_id
          AND environment_id = NEW.environment_id
          AND status = 'active'
    )
    BEGIN
        SELECT RAISE(ABORT, 'Workspace requires an active Project/Environment association');
    END;

    CREATE INDEX atlas_workspaces_by_owner
        ON atlas_workspaces(owner_user_id, status, workspace_id);
    CREATE INDEX atlas_workspaces_by_project_environment
        ON atlas_workspaces(project_id, environment_id, status);

    CREATE TRIGGER atlas_workspace_identity_immutable
    BEFORE UPDATE OF workspace_id, owner_user_id, project_id, environment_id, root_ref
    ON atlas_workspaces
    WHEN NEW.workspace_id != OLD.workspace_id
      OR NEW.owner_user_id != OLD.owner_user_id
      OR NEW.project_id != OLD.project_id
      OR NEW.environment_id != OLD.environment_id
      OR NEW.root_ref != OLD.root_ref
    BEGIN
        SELECT RAISE(ABORT, 'Workspace identity, owner, scope and root_ref are immutable');
    END;

    CREATE TRIGGER atlas_workspace_revision_step
    BEFORE UPDATE ON atlas_workspaces
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'Workspace revision must increase by exactly one');
    END;

    CREATE TRIGGER atlas_workspace_no_delete
    BEFORE DELETE ON atlas_workspaces
    BEGIN
        SELECT RAISE(ABORT, 'Workspaces are retained as authority tombstones');
    END;
    """,
)


# v19 introduces native Authentication Authority issuer metadata and immutable
# Identity Authority subject bindings. No identities or bindings are synthesized.
CORE_SCHEMA_V19 = SQLiteMigration(
    version=19,
    name="native_identity_issuers_and_subject_bindings",
    sql="""
    CREATE TABLE native_identity_issuers (
        issuer_id TEXT PRIMARY KEY CHECK (
            length(issuer_id) = 36
            AND issuer_id = lower(issuer_id)
            AND length(replace(issuer_id, '-', '')) = 32
            AND substr(issuer_id, 9, 1) = '-'
            AND substr(issuer_id, 14, 1) = '-'
            AND substr(issuer_id, 19, 1) = '-'
            AND substr(issuer_id, 24, 1) = '-'
            AND substr(issuer_id, 15, 1) = '4'
            AND substr(issuer_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND issuer_id NOT GLOB '*[^0-9a-f-]*'
        ),
        realm TEXT NOT NULL UNIQUE CHECK (
            length(realm) BETWEEN 2 AND 64
            AND realm = lower(realm)
            AND realm NOT GLOB '*[^a-z0-9._-]*'
            AND substr(realm, 1, 1) GLOB '[a-z0-9]'
        ),
        profile TEXT NOT NULL CHECK (profile = 'NATIVE_AUTHORITY_PROOF'),
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TRIGGER native_identity_issuer_identity_immutable
    BEFORE UPDATE OF issuer_id, realm, profile ON native_identity_issuers
    WHEN NEW.issuer_id != OLD.issuer_id
      OR NEW.realm != OLD.realm
      OR NEW.profile != OLD.profile
    BEGIN
        SELECT RAISE(ABORT, 'native issuer identity is immutable');
    END;

    CREATE TRIGGER native_identity_issuer_revision_step
    BEFORE UPDATE ON native_identity_issuers
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'native issuer revision must increase by exactly one');
    END;

    CREATE TRIGGER native_identity_issuer_revoked_terminal
    BEFORE UPDATE OF status ON native_identity_issuers
    WHEN OLD.status = 'REVOKED' AND NEW.status != 'REVOKED'
    BEGIN
        SELECT RAISE(ABORT, 'revoked native issuer is terminal');
    END;

    CREATE TRIGGER native_identity_issuer_no_delete
    BEFORE DELETE ON native_identity_issuers
    BEGIN
        SELECT RAISE(ABORT, 'native issuers are retained as tombstones');
    END;

    CREATE TABLE native_identity_bindings (
        binding_id TEXT PRIMARY KEY CHECK (
            length(binding_id) = 36
            AND binding_id = lower(binding_id)
            AND length(replace(binding_id, '-', '')) = 32
            AND substr(binding_id, 9, 1) = '-'
            AND substr(binding_id, 14, 1) = '-'
            AND substr(binding_id, 19, 1) = '-'
            AND substr(binding_id, 24, 1) = '-'
            AND substr(binding_id, 15, 1) = '4'
            AND substr(binding_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND binding_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_id TEXT NOT NULL,
        issuer_id TEXT NOT NULL,
        subject_digest TEXT NOT NULL CHECK (
            length(subject_digest) = 64
            AND subject_digest NOT GLOB '*[^0-9a-f]*'
        ),
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        revoked_at TEXT,
        UNIQUE (issuer_id, subject_digest),
        FOREIGN KEY (identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (issuer_id) REFERENCES native_identity_issuers(issuer_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        CHECK (
            (status = 'ACTIVE' AND revoked_at IS NULL)
            OR (status = 'REVOKED' AND revoked_at IS NOT NULL)
        )
    );

    CREATE INDEX native_identity_bindings_by_identity
        ON native_identity_bindings(identity_id, status);

    CREATE TRIGGER native_identity_binding_requires_active_user
    BEFORE INSERT ON native_identity_bindings
    WHEN NOT EXISTS (
        SELECT 1 FROM identity_records
        WHERE identity_id = NEW.identity_id
          AND identity_kind = 'user'
          AND identity_status = 'active'
    )
    BEGIN
        SELECT RAISE(ABORT, 'native binding requires an active canonical USER identity');
    END;

    CREATE TRIGGER native_identity_binding_requires_active_issuer
    BEFORE INSERT ON native_identity_bindings
    WHEN NOT EXISTS (
        SELECT 1 FROM native_identity_issuers
        WHERE issuer_id = NEW.issuer_id AND status = 'ACTIVE'
    )
    BEGIN
        SELECT RAISE(ABORT, 'native binding requires an active native issuer');
    END;

    CREATE TRIGGER native_identity_binding_identity_immutable
    BEFORE UPDATE OF binding_id, identity_id, issuer_id, subject_digest, created_at, verified_at
    ON native_identity_bindings
    WHEN NEW.binding_id != OLD.binding_id
      OR NEW.identity_id != OLD.identity_id
      OR NEW.issuer_id != OLD.issuer_id
      OR NEW.subject_digest != OLD.subject_digest
      OR NEW.created_at != OLD.created_at
      OR NEW.verified_at != OLD.verified_at
    BEGIN
        SELECT RAISE(ABORT, 'native identity binding identity is immutable');
    END;

    CREATE TRIGGER native_identity_binding_revision_step
    BEFORE UPDATE ON native_identity_bindings
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'native identity binding revision must increase by exactly one');
    END;

    CREATE TRIGGER native_identity_binding_revoked_terminal
    BEFORE UPDATE OF status ON native_identity_bindings
    WHEN OLD.status = 'REVOKED' AND NEW.status != 'REVOKED'
    BEGIN
        SELECT RAISE(ABORT, 'revoked native identity binding is terminal');
    END;

    CREATE TRIGGER native_identity_binding_no_delete
    BEFORE DELETE ON native_identity_bindings
    BEGIN
        SELECT RAISE(ABORT, 'native identity bindings are retained as tombstones');
    END;
    """,
)


CORE_SCHEMA_V20 = SQLiteMigration(
    version=20,
    name="native_authenticators_and_one_shot_proofs",
    sql="""
    CREATE TABLE native_authenticators (
        authenticator_id TEXT PRIMARY KEY CHECK (
            length(authenticator_id) = 36
            AND authenticator_id = lower(authenticator_id)
            AND length(replace(authenticator_id, '-', '')) = 32
            AND substr(authenticator_id, 15, 1) = '4'
            AND substr(authenticator_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND authenticator_id NOT GLOB '*[^0-9a-f-]*'
        ),
        issuer_id TEXT NOT NULL,
        native_subject TEXT NOT NULL CHECK (
            length(native_subject) = 43
            AND native_subject NOT GLOB '*[^A-Za-z0-9_-]*'
        ),
        login_handle TEXT NOT NULL CHECK (
            length(login_handle) BETWEEN 3 AND 64
            AND login_handle = lower(login_handle)
            AND login_handle NOT GLOB '*[^a-z0-9._-]*'
            AND substr(login_handle, 1, 1) GLOB '[a-z0-9]'
        ),
        password_hash_phc TEXT NOT NULL CHECK (
            substr(password_hash_phc, 1, 15) = '$argon2id$v=19$'
        ),
        credential_revision INTEGER NOT NULL CHECK (credential_revision > 0),
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (issuer_id, native_subject),
        UNIQUE (issuer_id, login_handle),
        UNIQUE (authenticator_id, issuer_id, native_subject),
        FOREIGN KEY (issuer_id) REFERENCES native_identity_issuers(issuer_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TRIGGER native_authenticator_requires_active_issuer
    BEFORE INSERT ON native_authenticators
    WHEN NOT EXISTS (
        SELECT 1 FROM native_identity_issuers
        WHERE issuer_id = NEW.issuer_id AND status = 'ACTIVE'
    )
    BEGIN
        SELECT RAISE(ABORT, 'native authenticator requires active issuer');
    END;

    CREATE TRIGGER native_authenticator_identity_immutable
    BEFORE UPDATE OF authenticator_id, issuer_id, native_subject ON native_authenticators
    WHEN NEW.authenticator_id != OLD.authenticator_id
      OR NEW.issuer_id != OLD.issuer_id
      OR NEW.native_subject != OLD.native_subject
    BEGIN
        SELECT RAISE(ABORT, 'native authenticator identity is immutable');
    END;

    CREATE TRIGGER native_authenticator_credential_revision
    BEFORE UPDATE ON native_authenticators
    WHEN (
        NEW.password_hash_phc != OLD.password_hash_phc
        AND NEW.credential_revision != OLD.credential_revision + 1
    ) OR (
        NEW.password_hash_phc = OLD.password_hash_phc
        AND NEW.credential_revision != OLD.credential_revision
    )
    BEGIN
        SELECT RAISE(ABORT, 'credential revision must advance exactly once when PHC changes');
    END;

    CREATE TRIGGER native_authenticator_revoked_terminal
    BEFORE UPDATE OF status ON native_authenticators
    WHEN OLD.status = 'REVOKED' AND NEW.status != 'REVOKED'
    BEGIN
        SELECT RAISE(ABORT, 'revoked native authenticator is terminal');
    END;

    CREATE TRIGGER native_authenticator_no_delete
    BEFORE DELETE ON native_authenticators
    BEGIN
        SELECT RAISE(ABORT, 'native authenticators are retained as tombstones');
    END;

    CREATE TABLE native_authentication_proofs (
        proof_id TEXT PRIMARY KEY CHECK (
            length(proof_id) = 36
            AND proof_id = lower(proof_id)
            AND length(replace(proof_id, '-', '')) = 32
            AND substr(proof_id, 15, 1) = '4'
            AND substr(proof_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND proof_id NOT GLOB '*[^0-9a-f-]*'
        ),
        reference_digest TEXT NOT NULL UNIQUE CHECK (
            length(reference_digest) = 64
            AND reference_digest NOT GLOB '*[^0-9a-f]*'
        ),
        issuer_id TEXT NOT NULL,
        native_subject TEXT NOT NULL,
        authenticator_id TEXT NOT NULL,
        credential_revision INTEGER NOT NULL CHECK (credential_revision > 0),
        authenticated_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        audience TEXT NOT NULL CHECK (
            length(audience) BETWEEN 1 AND 128
            AND audience = lower(audience)
            AND substr(audience, 1, 1) GLOB '[a-z]'
            AND audience NOT GLOB '*[^a-z0-9._:-]*'
        ),
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'CONSUMED', 'EXPIRED', 'REVOKED')),
        CHECK (expires_at > authenticated_at),
        FOREIGN KEY (authenticator_id, issuer_id, native_subject)
            REFERENCES native_authenticators(authenticator_id, issuer_id, native_subject)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX native_authentication_proofs_pending_expiry
        ON native_authentication_proofs(status, expires_at);
    CREATE INDEX native_authentication_proofs_by_authenticator
        ON native_authentication_proofs(authenticator_id, status);

    CREATE TRIGGER native_proof_requires_current_active_authenticator
    BEFORE INSERT ON native_authentication_proofs
    WHEN NEW.status != 'PENDING' OR NOT EXISTS (
        SELECT 1 FROM native_authenticators AS a
        WHERE a.authenticator_id = NEW.authenticator_id
          AND a.issuer_id = NEW.issuer_id
          AND a.native_subject = NEW.native_subject
          AND a.credential_revision = NEW.credential_revision
          AND a.status = 'ACTIVE'
          AND EXISTS (
              SELECT 1 FROM native_identity_issuers AS i
              WHERE i.issuer_id = a.issuer_id AND i.status = 'ACTIVE'
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'native proof requires current active authenticator and issuer');
    END;

    CREATE TRIGGER native_proof_identity_immutable
    BEFORE UPDATE OF proof_id, reference_digest, issuer_id, native_subject,
        authenticator_id, credential_revision, authenticated_at, expires_at, audience
    ON native_authentication_proofs
    WHEN NEW.proof_id != OLD.proof_id
      OR NEW.reference_digest != OLD.reference_digest
      OR NEW.issuer_id != OLD.issuer_id
      OR NEW.native_subject != OLD.native_subject
      OR NEW.authenticator_id != OLD.authenticator_id
      OR NEW.credential_revision != OLD.credential_revision
      OR NEW.authenticated_at != OLD.authenticated_at
      OR NEW.expires_at != OLD.expires_at
      OR NEW.audience != OLD.audience
    BEGIN
        SELECT RAISE(ABORT, 'native proof identity is immutable');
    END;

    CREATE TRIGGER native_proof_terminal_status
    BEFORE UPDATE OF status ON native_authentication_proofs
    WHEN OLD.status != 'PENDING' OR NEW.status NOT IN ('CONSUMED', 'EXPIRED', 'REVOKED')
    BEGIN
        SELECT RAISE(ABORT, 'native proof terminal status cannot be changed');
    END;

    CREATE TRIGGER native_proof_no_delete
    BEFORE DELETE ON native_authentication_proofs
    BEGIN
        SELECT RAISE(ABORT, 'native proofs are retained as tombstones');
    END;

    CREATE TRIGGER native_authenticator_invalidates_pending_proofs
    AFTER UPDATE OF credential_revision, status ON native_authenticators
    WHEN NEW.credential_revision != OLD.credential_revision
      OR (OLD.status = 'ACTIVE' AND NEW.status != 'ACTIVE')
    BEGIN
        UPDATE native_authentication_proofs
        SET status = 'REVOKED'
        WHERE authenticator_id = NEW.authenticator_id AND status = 'PENDING';
    END;
    """,
)



CORE_SCHEMA_V21 = SQLiteMigration(
    version=21,
    name="canonical_native_agent_identity_bindings",
    sql="""
    CREATE TABLE native_agent_identity_bindings (
        binding_id TEXT PRIMARY KEY CHECK (
            length(binding_id) = 36
            AND binding_id = lower(binding_id)
            AND length(replace(binding_id, '-', '')) = 32
            AND substr(binding_id, 9, 1) = '-'
            AND substr(binding_id, 14, 1) = '-'
            AND substr(binding_id, 19, 1) = '-'
            AND substr(binding_id, 24, 1) = '-'
            AND substr(binding_id, 15, 1) = '4'
            AND substr(binding_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND binding_id NOT GLOB '*[^0-9a-f-]*'
        ),
        identity_id TEXT NOT NULL,
        issuer_id TEXT NOT NULL,
        subject_digest TEXT NOT NULL CHECK (
            length(subject_digest) = 64
            AND subject_digest NOT GLOB '*[^0-9a-f]*'
        ),
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        created_at TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        revoked_at TEXT,
        UNIQUE (issuer_id, subject_digest),
        FOREIGN KEY (identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (issuer_id) REFERENCES native_identity_issuers(issuer_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        CHECK (
            (status = 'ACTIVE' AND revoked_at IS NULL)
            OR (status = 'REVOKED' AND revoked_at IS NOT NULL)
        )
    );

    CREATE INDEX native_agent_identity_bindings_by_identity
        ON native_agent_identity_bindings(identity_id, status);

    CREATE TRIGGER native_agent_identity_binding_requires_active_agent
    BEFORE INSERT ON native_agent_identity_bindings
    WHEN NOT EXISTS (
        SELECT 1 FROM identity_records
        WHERE identity_id = NEW.identity_id
          AND identity_kind = 'agent'
          AND identity_status = 'active'
          AND user_id IS NULL
    )
    BEGIN
        SELECT RAISE(ABORT, 'native AGENT binding requires an active canonical AGENT identity');
    END;

    CREATE TRIGGER native_agent_identity_binding_requires_active_issuer
    BEFORE INSERT ON native_agent_identity_bindings
    WHEN NOT EXISTS (
        SELECT 1 FROM native_identity_issuers
        WHERE issuer_id = NEW.issuer_id AND status = 'ACTIVE'
    )
    BEGIN
        SELECT RAISE(ABORT, 'native AGENT binding requires an active native issuer');
    END;

    CREATE TRIGGER native_agent_identity_binding_identity_immutable
    BEFORE UPDATE OF binding_id, identity_id, issuer_id, subject_digest, created_at, verified_at
    ON native_agent_identity_bindings
    WHEN NEW.binding_id != OLD.binding_id
      OR NEW.identity_id != OLD.identity_id
      OR NEW.issuer_id != OLD.issuer_id
      OR NEW.subject_digest != OLD.subject_digest
      OR NEW.created_at != OLD.created_at
      OR NEW.verified_at != OLD.verified_at
    BEGIN
        SELECT RAISE(ABORT, 'native AGENT binding identity is immutable');
    END;

    CREATE TRIGGER native_agent_identity_binding_revision_step
    BEFORE UPDATE ON native_agent_identity_bindings
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'native AGENT binding revision must increase by exactly one');
    END;

    CREATE TRIGGER native_agent_identity_binding_revoked_terminal
    BEFORE UPDATE OF status ON native_agent_identity_bindings
    WHEN OLD.status = 'REVOKED' AND NEW.status != 'REVOKED'
    BEGIN
        SELECT RAISE(ABORT, 'revoked native AGENT binding is terminal');
    END;

    CREATE TRIGGER native_agent_identity_binding_no_delete
    BEFORE DELETE ON native_agent_identity_bindings
    BEGIN
        SELECT RAISE(ABORT, 'native AGENT bindings are retained as tombstones');
    END;
    """,
)



CORE_SCHEMA_V22 = SQLiteMigration(
    version=22,
    name="exclusive_native_subject_binding_kind",
    sql="""
    CREATE TRIGGER native_agent_subject_cannot_bind_user
    BEFORE INSERT ON native_agent_identity_bindings
    WHEN EXISTS (
        SELECT 1 FROM native_identity_bindings
        WHERE issuer_id = NEW.issuer_id AND subject_digest = NEW.subject_digest
    )
    BEGIN
        SELECT RAISE(ABORT, 'native subject is already bound to a USER identity');
    END;

    CREATE TRIGGER native_user_subject_cannot_bind_agent
    BEFORE INSERT ON native_identity_bindings
    WHEN EXISTS (
        SELECT 1 FROM native_agent_identity_bindings
        WHERE issuer_id = NEW.issuer_id AND subject_digest = NEW.subject_digest
    )
    BEGIN
        SELECT RAISE(ABORT, 'native subject is already bound to an AGENT identity');
    END;
    """,
)



CORE_SCHEMA_V23 = SQLiteMigration(
    version=23,
    name="canonical_agent_delegations",
    sql="""
    CREATE TABLE agent_delegations (
        delegation_id TEXT PRIMARY KEY CHECK (
            length(delegation_id) = 36
            AND delegation_id = lower(delegation_id)
            AND length(replace(delegation_id, '-', '')) = 32
            AND substr(delegation_id, 9, 1) = '-'
            AND substr(delegation_id, 14, 1) = '-'
            AND substr(delegation_id, 19, 1) = '-'
            AND substr(delegation_id, 24, 1) = '-'
            AND substr(delegation_id, 15, 1) = '4'
            AND substr(delegation_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND delegation_id NOT GLOB '*[^0-9a-f-]*'
        ),
        owner_user_id TEXT NOT NULL,
        owner_identity_id TEXT NOT NULL,
        agent_identity_id TEXT NOT NULL,
        grant_id TEXT NOT NULL,
        grant_revision INTEGER NOT NULL CHECK (grant_revision > 0),
        project_id TEXT NOT NULL CHECK (length(trim(project_id)) > 0),
        environment TEXT NOT NULL CHECK (length(trim(environment)) > 0),
        resource_type TEXT NOT NULL CHECK (length(trim(resource_type)) > 0),
        resource_ids_json TEXT NOT NULL CHECK (length(trim(resource_ids_json)) > 2),
        actions_json TEXT NOT NULL CHECK (length(trim(actions_json)) > 2),
        issuer_id TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        not_before TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_by_user_identity_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
        revision INTEGER NOT NULL CHECK (revision > 0),
        revoked_at TEXT,
        revoked_by_user_id TEXT,
        CHECK (owner_identity_id != agent_identity_id),
        CHECK (created_by_user_identity_id = owner_identity_id),
        CHECK (not_before >= issued_at),
        CHECK (expires_at > not_before),
        CHECK (
            (status = 'active' AND revoked_at IS NULL AND revoked_by_user_id IS NULL)
            OR
            (status = 'revoked' AND revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL)
        ),
        FOREIGN KEY (owner_user_id) REFERENCES atlas_users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (owner_identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (agent_identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (grant_id) REFERENCES authorization_grants(grant_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (issuer_id) REFERENCES native_identity_issuers(issuer_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (created_by_user_identity_id) REFERENCES identity_records(identity_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (revoked_by_user_id) REFERENCES atlas_users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX agent_delegations_owner ON agent_delegations(owner_user_id, status);
    CREATE INDEX agent_delegations_agent ON agent_delegations(agent_identity_id, status);
    CREATE INDEX agent_delegations_grant ON agent_delegations(grant_id, status);

    CREATE TRIGGER agent_delegation_requires_canonical_claims
    BEFORE INSERT ON agent_delegations
    WHEN NOT EXISTS (
        SELECT 1
        FROM atlas_users u
        JOIN identity_records owner_i
          ON owner_i.identity_id = u.identity_id
        JOIN identity_records agent_i
          ON agent_i.identity_id = NEW.agent_identity_id
        JOIN authorization_grants g
          ON g.grant_id = NEW.grant_id
        JOIN native_identity_issuers issuer
          ON issuer.issuer_id = NEW.issuer_id
        WHERE u.user_id = NEW.owner_user_id
          AND owner_i.identity_id = NEW.owner_identity_id
          AND owner_i.identity_kind = 'user'
          AND owner_i.identity_status = 'active'
          AND agent_i.identity_kind = 'agent'
          AND agent_i.identity_status = 'active'
          AND g.owner_user_id = NEW.owner_user_id
          AND g.subject_identity_id = NEW.agent_identity_id
          AND g.project_id = NEW.project_id
          AND g.environment = NEW.environment
          AND g.revision = NEW.grant_revision
          AND g.revoked_at IS NULL
          AND g.issued_at <= NEW.issued_at
          AND g.expires_at >= NEW.expires_at
          AND issuer.status = 'ACTIVE'
          AND EXISTS (
              SELECT 1 FROM native_agent_identity_bindings b
              WHERE b.identity_id = NEW.agent_identity_id
                AND b.issuer_id = NEW.issuer_id
                AND b.status = 'ACTIVE'
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'delegation claims do not match active canonical owner, agent, Grant and issuer');
    END;

    CREATE TRIGGER agent_delegation_resource_scope_within_grant
    BEFORE INSERT ON agent_delegations
    WHEN EXISTS (
        SELECT 1
        FROM json_each(NEW.resource_ids_json) delegated
        WHERE NOT EXISTS (
            SELECT 1
            FROM authorization_grants g, json_each(g.resource_ids_json) granted
            WHERE g.grant_id = NEW.grant_id
              AND granted.value = delegated.value
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'delegated resource scope exceeds canonical Grant');
    END;

    CREATE TRIGGER agent_delegation_actions_within_grant
    BEFORE INSERT ON agent_delegations
    WHEN EXISTS (
        SELECT 1
        FROM json_each(NEW.actions_json) delegated
        WHERE NOT EXISTS (
            SELECT 1
            FROM authorization_grants g, json_each(g.actions_json) granted
            WHERE g.grant_id = NEW.grant_id
              AND granted.value = delegated.value
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'delegated actions exceed canonical Grant');
    END;

    CREATE TRIGGER agent_delegation_identity_immutable
    BEFORE UPDATE OF delegation_id, owner_user_id, owner_identity_id,
        agent_identity_id, grant_id, grant_revision, project_id, environment,
        resource_type, resource_ids_json, actions_json, issuer_id, issued_at,
        not_before, expires_at, created_by_user_identity_id
    ON agent_delegations
    WHEN NEW.delegation_id != OLD.delegation_id
      OR NEW.owner_user_id != OLD.owner_user_id
      OR NEW.owner_identity_id != OLD.owner_identity_id
      OR NEW.agent_identity_id != OLD.agent_identity_id
      OR NEW.grant_id != OLD.grant_id
      OR NEW.grant_revision != OLD.grant_revision
      OR NEW.project_id != OLD.project_id
      OR NEW.environment != OLD.environment
      OR NEW.resource_type != OLD.resource_type
      OR NEW.resource_ids_json != OLD.resource_ids_json
      OR NEW.actions_json != OLD.actions_json
      OR NEW.issuer_id != OLD.issuer_id
      OR NEW.issued_at != OLD.issued_at
      OR NEW.not_before != OLD.not_before
      OR NEW.expires_at != OLD.expires_at
      OR NEW.created_by_user_identity_id != OLD.created_by_user_identity_id
    BEGIN
        SELECT RAISE(ABORT, 'delegation claims are immutable');
    END;

    CREATE TRIGGER agent_delegation_revision_step
    BEFORE UPDATE ON agent_delegations
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'delegation revision must increase by exactly one');
    END;

    CREATE TRIGGER agent_delegation_revocation_terminal
    BEFORE UPDATE OF status ON agent_delegations
    WHEN OLD.status = 'revoked' AND NEW.status != 'revoked'
    BEGIN
        SELECT RAISE(ABORT, 'revoked delegation is terminal');
    END;

    CREATE TRIGGER agent_delegation_no_delete
    BEFORE DELETE ON agent_delegations
    BEGIN
        SELECT RAISE(ABORT, 'delegations are retained as tombstones');
    END;
    """,
)


# v24 binds AGENT renewal requests to the exact Grant and owner delegation
# revisions that were revalidated and authorized at request time.
CORE_SCHEMA_V24 = SQLiteMigration(
    version=24,
    name="agent_grant_renewal_authority_evidence",
    sql="""
    ALTER TABLE authorization_grant_renewals
        ADD COLUMN grant_revision INTEGER
        CHECK (grant_revision IS NULL OR grant_revision > 0);
    ALTER TABLE authorization_grant_renewals
        ADD COLUMN delegation_id TEXT
        REFERENCES agent_delegations(delegation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;
    ALTER TABLE authorization_grant_renewals
        ADD COLUMN delegation_revision INTEGER
        CHECK (delegation_revision IS NULL OR delegation_revision > 0);

    CREATE TRIGGER authorization_grant_renewals_agent_evidence_complete
    BEFORE INSERT ON authorization_grant_renewals
    WHEN NOT (
        (NEW.grant_revision IS NULL AND NEW.delegation_id IS NULL
         AND NEW.delegation_revision IS NULL)
        OR
        (NEW.grant_revision IS NOT NULL AND NEW.delegation_id IS NOT NULL
         AND NEW.delegation_revision IS NOT NULL)
    )
    BEGIN
        SELECT RAISE(ABORT, 'AGENT renewal authority evidence must be complete');
    END;

    CREATE TRIGGER authorization_grant_renewals_agent_evidence_matches_authority
    BEFORE INSERT ON authorization_grant_renewals
    WHEN NEW.delegation_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1
        FROM agent_delegations d
        JOIN authorization_grants g ON g.grant_id = d.grant_id
        JOIN native_identity_issuers issuer ON issuer.issuer_id = d.issuer_id
        JOIN native_agent_identity_bindings binding
          ON binding.identity_id = d.agent_identity_id
         AND binding.issuer_id = d.issuer_id
        WHERE d.delegation_id = NEW.delegation_id
          AND d.revision = NEW.delegation_revision
          AND d.status = 'active'
          AND d.not_before <= NEW.requested_at
          AND d.expires_at > NEW.requested_at
          AND d.grant_id = NEW.grant_id
          AND d.grant_revision = NEW.grant_revision
          AND d.owner_user_id = NEW.owner_user_id
          AND d.agent_identity_id = NEW.subject_identity_id
          AND NEW.requested_by_identity_id = d.agent_identity_id
          AND d.project_id = g.project_id
          AND d.environment = g.environment
          AND d.resource_type = g.resource_type
          AND d.resource_ids_json = g.resource_ids_json
          AND EXISTS (
              SELECT 1 FROM json_each(g.actions_json)
              WHERE value = 'grant.renewal.request'
          )
          AND EXISTS (
              SELECT 1 FROM json_each(d.actions_json)
              WHERE value = 'grant.renewal.request'
          )
          AND g.owner_user_id = NEW.owner_user_id
          AND g.subject_identity_id = NEW.subject_identity_id
          AND g.revision = NEW.grant_revision
          AND g.expires_at = NEW.current_expires_at
          AND g.issued_at <= NEW.requested_at
          AND g.expires_at > NEW.requested_at
          AND g.revoked_at IS NULL
          AND issuer.status = 'ACTIVE'
          AND binding.status = 'ACTIVE'
      )
    BEGIN
        SELECT RAISE(ABORT, 'AGENT renewal evidence does not match active canonical authority');
    END;

    CREATE TRIGGER authorization_grant_renewals_agent_evidence_immutable
    BEFORE UPDATE OF grant_revision, delegation_id, delegation_revision
    ON authorization_grant_renewals
    WHEN NEW.grant_revision IS NOT OLD.grant_revision
      OR NEW.delegation_id IS NOT OLD.delegation_id
      OR NEW.delegation_revision IS NOT OLD.delegation_revision
    BEGIN
        SELECT RAISE(ABORT, 'Grant renewal authority evidence is immutable');
    END;

    CREATE INDEX authorization_grant_renewals_delegation
        ON authorization_grant_renewals(delegation_id, delegation_revision);
    """,
)


SQLITE_MIGRATIONS = (
    CORE_SCHEMA_V1, CORE_SCHEMA_V2, CORE_SCHEMA_V3, CORE_SCHEMA_V4,
    CORE_SCHEMA_V5, CORE_SCHEMA_V6, CORE_SCHEMA_V7, CORE_SCHEMA_V8,
    CORE_SCHEMA_V9, CORE_SCHEMA_V10, CORE_SCHEMA_V11, CORE_SCHEMA_V12, CORE_SCHEMA_V13, CORE_SCHEMA_V14, CORE_SCHEMA_V15, CORE_SCHEMA_V16, CORE_SCHEMA_V17, CORE_SCHEMA_V18, CORE_SCHEMA_V19, CORE_SCHEMA_V20, CORE_SCHEMA_V21, CORE_SCHEMA_V22, CORE_SCHEMA_V23, CORE_SCHEMA_V24,
)
