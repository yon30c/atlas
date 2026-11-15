"""SQLite persistence adapter for the canonical internal Identity Authority."""
from datetime import datetime, timezone
import sqlite3
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
    NotFoundError,
)
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.user_identity import (
    CanonicalUserIdentity,
    validate_canonical_uuid4,
)
from atlas.ports.identity_authority import IdentityAuthorityPort


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SQLiteIdentityAuthority(IdentityAuthorityPort):
    """The sole local issuer of canonical UserId and Identity(USER) records.

    The adapter intentionally has no external issuer, binding, authentication,
    recovery, or authorization responsibilities.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CanonicalUserIdentity:
        return CanonicalUserIdentity(
            user_id=row["user_id"],
            identity=Identity(
                identity_id=row["identity_id"],
                kind=IdentityKind(row["identity_kind"]),
                status=IdentityStatus(row["identity_status"]),
                revision=row["revision"],
            ),
        )

    @staticmethod
    def _select_user(connection: sqlite3.Connection, user_id: str):
        return connection.execute(
            """
            SELECT u.user_id, i.identity_id, i.identity_kind,
                   i.identity_status, i.revision
            FROM atlas_users AS u
            JOIN identity_records AS i ON i.identity_id = u.identity_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()

    def create_user(self) -> CanonicalUserIdentity:
        """Generate both UUIDv4 identifiers and persist the pair atomically."""
        user_id = str(uuid4())
        identity_id = str(uuid4())
        now = _utc_now_text()
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status,
                        revision, created_at, updated_at, user_id
                    ) VALUES (?, 'user', 'active', 1, ?, ?, ?)
                    """,
                    (identity_id, now, now, user_id),
                )
                connection.execute(
                    """
                    INSERT INTO atlas_users (user_id, identity_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, identity_id, now),
                )
                row = self._select_user(connection, user_id)
                if row is None:
                    raise sqlite3.DatabaseError(
                        "la creación canónica no pudo releer su relación UserId/Identity"
                    )
                return self._from_row(row)
        except sqlite3.IntegrityError as exc:
            # Never retry with a replacement identifier or overwrite an existing row.
            raise IdentityConflictError(
                "conflicto de unicidad o integridad al crear la identidad canónica"
            ) from exc

    def get_user(self, user_id: str) -> CanonicalUserIdentity | None:
        validate_canonical_uuid4(user_id, "user_id")
        with self._database.connection() as connection:
            row = self._select_user(connection, user_id)
            return None if row is None else self._from_row(row)

    def update_user_status(
        self,
        user_id: str,
        *,
        expected_revision: int,
        status: IdentityStatus,
    ) -> CanonicalUserIdentity:
        validate_canonical_uuid4(user_id, "user_id")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if not isinstance(status, IdentityStatus):
            raise ContractError("status debe ser IdentityStatus")

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            row = self._select_user(connection, user_id)
            if row is None:
                raise NotFoundError("usuario canónico no encontrado")
            current = self._from_row(row)
            if current.identity.revision != expected_revision:
                raise ConcurrencyError("revisión de identidad obsoleta")
            if (
                current.identity.status is IdentityStatus.REVOKED
                and status is not IdentityStatus.REVOKED
            ):
                raise ContractError("una identidad revocada es terminal")
            if current.identity.status is status:
                return current

            cursor = connection.execute(
                """
                UPDATE identity_records
                SET identity_status = ?, revision = revision + 1, updated_at = ?
                WHERE identity_id = ? AND revision = ?
                """,
                (
                    status.value,
                    _utc_now_text(),
                    current.identity.identity_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError("la identidad cambió durante la actualización")
            updated = self._select_user(connection, user_id)
            if updated is None:
                raise sqlite3.DatabaseError(
                    "la identidad canónica desapareció durante una actualización"
                )
            return self._from_row(updated)
