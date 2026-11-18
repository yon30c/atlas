"""Offline-only SQLite writer for the first Platform Admin grant.

This adapter is intentionally not composed into runtime unit-of-work factories.
It owns one BEGIN IMMEDIATE transaction per provisioning attempt.
"""

from datetime import datetime, timedelta
import json
import sqlite3

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.core.errors import AuthorizationError, ConcurrencyError, ContractError
from atlas.core.identity import IdentityStatus
from atlas.core.platform_admin import (
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminPermission,
)
from atlas.ports.platform_admin_authority import PlatformAdminBootstrapPort
from atlas.core.user_identity import validate_canonical_uuid4


def _timestamp(value, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe ser datetime UTC")
    return value.isoformat(timespec="microseconds")


class SQLitePlatformAdminBootstrapAdapter(PlatformAdminBootstrapPort):
    """Persist the unique first administrator, only from an offline tool."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _same_operation(row: sqlite3.Row, command: PlatformAdminBootstrapCommand) -> bool:
        request = command.request
        provenance = command.provenance
        grant = command.grant
        expected_permissions = json.dumps(
            sorted(permission.value for permission in request.permissions),
            separators=(",", ":"),
        )
        return (
            row["event_id"] == provenance.event_id
            and row["grant_id"] == provenance.grant_id
            and row["user_id"] == request.user_id
            and row["user_identity_id"] == grant.user_identity_id
            and row["user_identity_revision"] == grant.user_identity_revision
            and row["operator_real_uid"] == provenance.operator_real_uid
            and row["operator_effective_uid"] == provenance.operator_effective_uid
            and row["terminal_id"] == provenance.terminal_id
            and row["confirmed_at"] == _timestamp(provenance.confirmed_at, "confirmed_at")
            and row["grant_permissions_json"] == expected_permissions
            and row["provisioning_method"] == grant.provisioning_method.value
            and row["issued_at"] == _timestamp(grant.issued_at, "issued_at")
            and row["not_before"] == _timestamp(grant.not_before, "not_before")
            and row["expires_at"] == _timestamp(grant.expires_at, "expires_at")
        )

    @staticmethod
    def _load_grant(connection: sqlite3.Connection, grant_id: str) -> PlatformAdminGrant:
        from atlas.adapters.sqlite.platform_admin_authority import (
            SQLitePlatformAdminAuthorityReader,
        )

        row = connection.execute(
            "SELECT * FROM platform_admin_grants WHERE grant_id = ?",
            (grant_id,),
        ).fetchone()
        if row is None:
            raise ContractError("bootstrap operation references a missing grant")
        # Keep row decoding in the canonical read adapter.
        return SQLitePlatformAdminAuthorityReader._from_row(row)

    def get_operation(
        self,
        operation_id: str,
    ) -> PlatformAdminBootstrapCommand | None:
        """Recover the exact persisted command for an offline retry."""
        validate_canonical_uuid4(operation_id, "operation_id")
        from atlas.adapters.sqlite.platform_admin_authority import (
            SQLitePlatformAdminAuthorityReader,
        )

        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT e.*, g.permissions_json AS grant_permissions_json
                FROM platform_admin_bootstrap_events AS e
                JOIN platform_admin_grants AS g ON g.grant_id = e.grant_id
                WHERE e.operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if row is None:
                return None
            try:
                permission_values = json.loads(row["grant_permissions_json"])
                if not isinstance(permission_values, list):
                    raise ValueError("permissions_json is not an array")
                permissions = frozenset(
                    PlatformAdminPermission(value) for value in permission_values
                )
                request = PlatformAdminBootstrapRequest(
                    operation_id=row["operation_id"],
                    user_id=row["user_id"],
                    permissions=permissions,
                )
                provenance = PlatformAdminBootstrapProvenance(
                    event_id=row["event_id"],
                    grant_id=row["grant_id"],
                    operator_real_uid=row["operator_real_uid"],
                    operator_effective_uid=row["operator_effective_uid"],
                    terminal_id=row["terminal_id"],
                    confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
                )
                grant_row = connection.execute(
                    "SELECT * FROM platform_admin_grants WHERE grant_id = ?",
                    (row["grant_id"],),
                ).fetchone()
                if grant_row is None:
                    raise ValueError("bootstrap event has no grant")
                grant = SQLitePlatformAdminAuthorityReader._from_row(grant_row)
                return PlatformAdminBootstrapCommand(
                    request=request,
                    provenance=provenance,
                    grant=grant,
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise ContractError(
                    "operación Platform Admin persistida es inválida"
                ) from exc

    def provision_first_admin(
        self,
        command: PlatformAdminBootstrapCommand,
    ) -> PlatformAdminGrant:
        if not isinstance(command, PlatformAdminBootstrapCommand):
            raise ContractError("command debe ser PlatformAdminBootstrapCommand")
        request = command.request
        provenance = command.provenance
        grant = command.grant
        validate_canonical_uuid4(request.operation_id, "operation_id")

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)

            # Idempotency lookup MUST precede the historical-bootstrap guard.
            prior = connection.execute(
                """
                SELECT e.*, g.permissions_json AS grant_permissions_json,
                       g.provisioning_method, g.issued_at, g.not_before,
                       g.expires_at
                FROM platform_admin_bootstrap_events AS e
                JOIN platform_admin_grants AS g
                  ON g.grant_id = e.grant_id
                WHERE e.operation_id = ?
                """,
                (request.operation_id,),
            ).fetchone()
            if prior is not None:
                if not self._same_operation(prior, command):
                    raise ConcurrencyError(
                        "operation_id ya existe con una intención o procedencia diferente"
                    )
                return self._load_grant(connection, prior["grant_id"])

            history = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM platform_admin_bootstrap_events)
                    +
                    (SELECT COUNT(*) FROM platform_admin_grants)
                """
            ).fetchone()[0]
            if history:
                raise AuthorizationError(
                    "el bootstrap inicial ya fue utilizado; no se permite recuperar "
                    "o reemplazar administradores mediante este mecanismo"
                )

            canonical = SQLiteIdentityAuthority(
                self._database,
                unit_of_work=unit,
            ).get_user(request.user_id)
            if canonical is None:
                raise AuthorizationError("el USER canónico solicitado no existe")
            if canonical.identity.status is not IdentityStatus.ACTIVE:
                raise AuthorizationError("el USER canónico no está activo")
            if (
                canonical.identity.identity_id != grant.user_identity_id
                or canonical.identity.revision != grant.user_identity_revision
            ):
                raise ConcurrencyError(
                    "la identidad USER canónica cambió desde la preparación del bootstrap"
                )

            values = (
                provenance.event_id,
                provenance.grant_id,
                request.user_id,
                canonical.identity.identity_id,
                canonical.identity.revision,
                request.operation_id,
                provenance.operator_real_uid,
                provenance.operator_effective_uid,
                provenance.terminal_id,
                _timestamp(provenance.confirmed_at, "confirmed_at"),
            )
            try:
                connection.execute(
                    """
                    INSERT INTO platform_admin_bootstrap_events (
                        event_id, grant_id, user_id, user_identity_id,
                        user_identity_revision, operation_id, operator_real_uid,
                        operator_effective_uid, terminal_id, confirmed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                connection.execute(
                    """
                    INSERT INTO platform_admin_grants (
                        grant_id, user_id, user_identity_id, user_identity_revision,
                        permissions_json, provisioning_method, bootstrap_event_id,
                        issued_at, not_before, expires_at, status, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1)
                    """,
                    (
                        grant.grant_id,
                        grant.user_id,
                        grant.user_identity_id,
                        grant.user_identity_revision,
                        json.dumps(
                            sorted(permission.value for permission in grant.permissions),
                            separators=(",", ":"),
                        ),
                        grant.provisioning_method.value,
                        grant.bootstrap_event_id,
                        _timestamp(grant.issued_at, "issued_at"),
                        _timestamp(grant.not_before, "not_before"),
                        _timestamp(grant.expires_at, "expires_at"),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError(
                    "la base rechazó la integridad del bootstrap Platform Admin"
                ) from exc

            persisted = self._load_grant(connection, grant.grant_id)
            if persisted != grant:
                raise ContractError("la concesión persistida no coincide con el comando")
            return persisted
