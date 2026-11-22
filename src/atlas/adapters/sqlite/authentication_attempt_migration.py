"""V28: durable account-scoped authentication attempt reservations and failures."""

from atlas.adapters.sqlite.database import SQLiteMigration


CORE_SCHEMA_V28 = SQLiteMigration(
    version=28,
    name="atomic_native_authentication_attempt_reservations",
    sql="""
    CREATE TABLE native_authentication_attempt_reservations (
        reservation_id TEXT PRIMARY KEY CHECK (
            length(reservation_id) = 36
            AND reservation_id = lower(reservation_id)
            AND substr(reservation_id, 15, 1) = '4'
            AND substr(reservation_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND reservation_id NOT GLOB '*[^0-9a-f-]*'
        ),
        account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
        expires_at TEXT NOT NULL CHECK (length(expires_at) = 32)
    );

    CREATE INDEX native_authentication_attempt_reservations_by_account
        ON native_authentication_attempt_reservations(account_digest, expires_at);

    CREATE INDEX native_authentication_attempt_reservations_by_expiry
        ON native_authentication_attempt_reservations(expires_at);

    CREATE TABLE native_authentication_attempt_failures (
        failure_id TEXT PRIMARY KEY CHECK (
            length(failure_id) = 36
            AND failure_id = lower(failure_id)
            AND substr(failure_id, 15, 1) = '4'
            AND substr(failure_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND failure_id NOT GLOB '*[^0-9a-f-]*'
        ),
        account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
        occurred_at TEXT NOT NULL CHECK (length(occurred_at) = 32),
        blocked_until TEXT NOT NULL CHECK (length(blocked_until) = 32)
    );

    CREATE INDEX native_authentication_attempt_failures_by_account_window
        ON native_authentication_attempt_failures(account_digest, occurred_at, blocked_until);

    CREATE INDEX native_authentication_attempt_failures_by_retention
        ON native_authentication_attempt_failures(occurred_at, blocked_until);
    """,
)
