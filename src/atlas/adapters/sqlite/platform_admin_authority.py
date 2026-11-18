"""Read-only SQLite adapter for canonical Platform Admin grants."""

from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.errors import ContractError
from atlas.core.platform_admin import (
    PlatformAdminGrant,
    PlatformAdminGrantStatus,
    PlatformAdminPermission,
    PlatformAdminProvisioningMethod,
)
from atlas.core.user_identity import validate_canonical_uuid4
from atlas.ports.platform_admin_authority import PlatformAdminAuthorityReaderPort


class SQLitePlatformAdminAuthorityReader(PlatformAdminAuthorityReaderPort):
    """Read grants only; deliberately exposes no provisioning or mutation API."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        unit_of_work: SQLiteUnitOfWork | None = None,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if unit_of_work is not None and not isinstance(unit_of_work, SQLiteUnitOfWork):
            raise ContractError("unit_of_work debe ser SQLiteUnitOfWork")
        self._database = database
        self._unit_of_work = unit_of_work

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.connection() as connection:
                yield connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PlatformAdminGrant:
        try:
            raw_permissions = json.loads(row["permissions_json"])
            if not isinstance(raw_permissions, list):
                raise ValueError("permissions_json is not an array")
            permissions = frozenset(
                PlatformAdminPermission(value) for value in raw_permissions
            )
            return PlatformAdminGrant(
                grant_id=row["grant_id"],
                user_id=row["user_id"],
                user_identity_id=row["user_identity_id"],
                user_identity_revision=row["user_identity_revision"],
                permissions=permissions,
                provisioning_method=PlatformAdminProvisioningMethod(
                    row["provisioning_method"]
                ),
                bootstrap_event_id=row["bootstrap_event_id"],
                issued_at=datetime.fromisoformat(row["issued_at"]),
                not_before=datetime.fromisoformat(row["not_before"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                status=PlatformAdminGrantStatus(row["status"]),
                revision=row["revision"],
                revoked_at=(
                    None if row["revoked_at"] is None
                    else datetime.fromisoformat(row["revoked_at"])
                ),
                revoked_by_user_id=row["revoked_by_user_id"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro Platform Admin persistido es inválido") from exc

    def get_grant(self, grant_id: str) -> PlatformAdminGrant | None:
        validate_canonical_uuid4(grant_id, "grant_id")
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM platform_admin_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
            return None if row is None else self._from_row(row)

    def list_grants_for_user(
        self, user_id: str
    ) -> tuple[PlatformAdminGrant, ...]:
        validate_canonical_uuid4(user_id, "user_id")
        with self._read_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM platform_admin_grants
                   WHERE user_id = ? ORDER BY grant_id""",
                (user_id,),
            ).fetchall()
            return tuple(self._from_row(row) for row in rows)
