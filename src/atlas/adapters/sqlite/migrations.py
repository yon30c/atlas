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



# v6 closes the identity relation in both directions at transaction commit.
# Existing USER rows are backfilled; orphaned legacy identities abort the migration.
CORE_SCHEMA_V6 = SQLiteMigration(
    version=6,
    name="bidirectional_user_identity_integrity",
    sql="""
    PRAGMA defer_foreign_keys = ON;

    ALTER TABLE identity_records ADD COLUMN user_id TEXT
        REFERENCES atlas_users(user_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED;

    DROP TRIGGER identity_records_revision_step;

    CREATE TRIGGER identity_records_user_link_kind_insert
    BEFORE INSERT ON identity_records
    WHEN (NEW.identity_kind = 'user' AND NEW.user_id IS NULL)
      OR (NEW.identity_kind != 'user' AND NEW.user_id IS NOT NULL)
    BEGIN
        SELECT RAISE(ABORT, 'only USER identities may reference atlas_users');
    END;

    CREATE TRIGGER identity_records_user_link_kind_update
    BEFORE UPDATE OF identity_kind, user_id ON identity_records
    WHEN (NEW.identity_kind = 'user' AND NEW.user_id IS NULL)
      OR (NEW.identity_kind != 'user' AND NEW.user_id IS NOT NULL)
    BEGIN
        SELECT RAISE(ABORT, 'identity kind and user link are inconsistent');
    END;

    UPDATE identity_records
    SET user_id = (
        SELECT atlas_users.user_id
        FROM atlas_users
        WHERE atlas_users.identity_id = identity_records.identity_id
    )
    WHERE identity_kind = 'user';

    CREATE UNIQUE INDEX identity_records_user_id_unique
        ON identity_records(user_id);

    CREATE UNIQUE INDEX identity_records_identity_user_unique
        ON identity_records(identity_id, user_id);

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
            REFERENCES identity_records(identity_id, user_id)
            ON UPDATE NO ACTION ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
    );

    INSERT INTO atlas_users_v6 (user_id, identity_id, created_at)
    SELECT user_id, identity_id, created_at
    FROM atlas_users;

    DROP TABLE atlas_users;
    ALTER TABLE atlas_users_v6 RENAME TO atlas_users;

    CREATE TRIGGER identity_records_revision_step
    BEFORE UPDATE ON identity_records
    WHEN NEW.revision != OLD.revision + 1
    BEGIN
        SELECT RAISE(ABORT, 'identity revision must increase by exactly one');
    END;

    CREATE TRIGGER identity_records_user_id_immutable
    BEFORE UPDATE OF user_id ON identity_records
    WHEN NEW.user_id != OLD.user_id
    BEGIN
        SELECT RAISE(ABORT, 'identity user_id is immutable');
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
    """,
)


SQLITE_MIGRATIONS = (
    CORE_SCHEMA_V1, CORE_SCHEMA_V2, CORE_SCHEMA_V3, CORE_SCHEMA_V4,
    CORE_SCHEMA_V5, CORE_SCHEMA_V6,
)

    CORE_SCHEMA_V1, CORE_SCHEMA_V2, CORE_SCHEMA_V3, CORE_SCHEMA_V4,
    CORE_SCHEMA_V5,
)

