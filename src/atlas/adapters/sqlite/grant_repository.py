"""SQLite persistence adapter for canonical CAM Grants."""

from datetime import datetime
import json
import sqlite3

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.ports.grants import GrantRepository


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


class SQLiteGrantRepository(GrantRepository):
    """Stores each Grant and its exact revision in one canonical SQLite row.

    The adapter is bound to one database instance. Updates require the caller
    to provide the next revision, and the SQL predicate compares the stored
    previous revision to prevent lost updates.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Grant:
        try:
            resource_ids = json.loads(row["resource_ids_json"])
            actions = json.loads(row["actions_json"])
            if (
                not isinstance(resource_ids, list)
                or not isinstance(actions, list)
                or any(not isinstance(item, str) for item in resource_ids)
                or any(not isinstance(item, str) for item in actions)
            ):
                raise ValueError("invalid permission collections")
            return Grant(
                grant_id=row["grant_id"],
                owner_user_id=row["owner_user_id"],
                subject_identity_id=row["subject_identity_id"],
                project_id=row["project_id"],
                environment=row["environment"],
                resource_scope=GrantResourceScope(
                    resource_type=row["resource_type"],
                    resource_ids=frozenset(resource_ids),
                ),
                actions=frozenset(actions),
                issued_at=datetime.fromisoformat(row["issued_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                revoked_at=(
                    None if row["revoked_at"] is None
                    else datetime.fromisoformat(row["revoked_at"])
                ),
                revision=row["revision"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro Grant SQLite corrupto o inválido") from exc

    @staticmethod
    def _values(grant: Grant) -> tuple[object, ...]:
        if not isinstance(grant, Grant):
            raise ContractError("grant debe ser Grant")
        return (
            grant.grant_id,
            grant.owner_user_id,
            grant.subject_identity_id,
            grant.project_id,
            grant.environment,
            grant.resource_type,
            json.dumps(sorted(grant.resource_ids), ensure_ascii=False, separators=(",", ":")),
            json.dumps(sorted(grant.actions), ensure_ascii=False, separators=(",", ":")),
            _timestamp(grant.issued_at),
            _timestamp(grant.expires_at),
            None if grant.revoked_at is None else _timestamp(grant.revoked_at),
            grant.revision,
        )

    def create(self, grant: Grant) -> None:
        values = self._values(grant)
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                connection.execute(
                    """
                    INSERT INTO authorization_grants (
                        grant_id, owner_user_id, subject_identity_id, project_id,
                        environment, resource_type, resource_ids_json, actions_json,
                        issued_at, expires_at, revoked_at, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("No se pudo crear el Grant por conflicto de integridad") from exc

    def get(self, grant_id: str) -> Grant | None:
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ContractError("grant_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM authorization_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, grant: Grant) -> None:
        values = self._values(grant)
        if grant.revision < 2:
            raise ContractError("una actualización debe incrementar la revisión")
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                cursor = connection.execute(
                    """
                    UPDATE authorization_grants
                    SET owner_user_id = ?, subject_identity_id = ?, project_id = ?,
                        environment = ?, resource_type = ?, resource_ids_json = ?,
                        actions_json = ?, issued_at = ?, expires_at = ?,
                        revoked_at = ?, revision = ?
                    WHERE grant_id = ? AND revision = ?
                    """,
                    (*values[1:], values[0], grant.revision - 1),
                )
                if cursor.rowcount != 1:
                    row = connection.execute(
                        "SELECT revision FROM authorization_grants WHERE grant_id = ?",
                        (grant.grant_id,),
                    ).fetchone()
                    if row is None:
                        raise NotFoundError("Grant no encontrado")
                    raise ConcurrencyError("la revisión del Grant cambió")
        except sqlite3.IntegrityError as exc:
            raise ContractError("La actualización viola la integridad del Grant") from exc

    def list_by_owner(self, owner_user_id: str) -> tuple[Grant, ...]:
        if not isinstance(owner_user_id, str) or not owner_user_id.strip():
            raise ContractError("owner_user_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM authorization_grants
                WHERE owner_user_id = ? ORDER BY grant_id
                """,
                (owner_user_id,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)
