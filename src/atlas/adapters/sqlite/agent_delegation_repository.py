"""SQLite repository for immutable owner-issued AGENT delegation records.

This is a persistence primitive, not an owner-authentication or CAM authority.
Callers must verify owner evidence before invoking create/update. The adapter
rechecks canonical owner, AGENT, native issuer/binding and exact Grant claims
inside the same SQLite transaction as the write.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
import json
import sqlite3
from typing import Iterator
from uuid import UUID

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
    validate_agent_delegation_transition,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.core.user_identity import validate_canonical_uuid4


def _timestamp(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe ser datetime UTC")
    return value.isoformat(timespec="microseconds")


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} persistido inválido") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{field} persistido no está en UTC")
    return parsed


class SQLiteAgentDelegationRepository:
    """Persists canonical delegation claims and terminal revocation tombstones."""

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

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.unit_of_work() as unit:
                yield unit._connection_for(self._database)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentDelegation:
        try:
            resource_ids = json.loads(row["resource_ids_json"])
            actions = json.loads(row["actions_json"])
            if (
                not isinstance(resource_ids, list)
                or not isinstance(actions, list)
                or any(not isinstance(item, str) for item in resource_ids)
                or any(not isinstance(item, str) for item in actions)
            ):
                raise ValueError("invalid delegation scope")
            return AgentDelegation(
                delegation_id=row["delegation_id"],
                owner_user_id=row["owner_user_id"],
                owner_identity_id=row["owner_identity_id"],
                agent_identity_id=row["agent_identity_id"],
                grant_id=row["grant_id"],
                grant_revision=row["grant_revision"],
                project_id=row["project_id"],
                environment=row["environment"],
                scope=AgentDelegationScope(
                    resource_type=row["resource_type"],
                    resource_ids=frozenset(resource_ids),
                    actions=frozenset(actions),
                ),
                issuer_id=row["issuer_id"],
                issued_at=_parse_timestamp(row["issued_at"], "issued_at"),
                not_before=_parse_timestamp(row["not_before"], "not_before"),
                expires_at=_parse_timestamp(row["expires_at"], "expires_at"),
                created_by_user_identity_id=row["created_by_user_identity_id"],
                status=AgentDelegationStatus(row["status"]),
                revision=row["revision"],
                revoked_at=(
                    None if row["revoked_at"] is None
                    else _parse_timestamp(row["revoked_at"], "revoked_at")
                ),
                revoked_by_user_id=row["revoked_by_user_id"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro de delegación SQLite corrupto o inválido") from exc

    @staticmethod
    def _validate_grant_subset(connection: sqlite3.Connection, delegation: AgentDelegation) -> None:
        row = connection.execute(
            "SELECT * FROM authorization_grants WHERE grant_id = ?",
            (delegation.grant_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("Grant canónico no encontrado")
        try:
            grant_resource_ids = json.loads(row["resource_ids_json"])
            grant_actions = json.loads(row["actions_json"])
        except (TypeError, ValueError):
            raise ContractError("scope del Grant persistido está corrupto") from None
        if (
            row["owner_user_id"] != delegation.owner_user_id
            or row["subject_identity_id"] != delegation.agent_identity_id
            or row["project_id"] != delegation.project_id
            or row["environment"] != delegation.environment
            or row["resource_type"] != delegation.scope.resource_type
            or row["revision"] != delegation.grant_revision
            or row["revoked_at"] is not None
        ):
            raise ContractError("la delegación no coincide con el Grant canónico vigente")
        if not delegation.scope.resource_ids.issubset(frozenset(grant_resource_ids)):
            raise ContractError("la delegación amplía el alcance de recursos del Grant")
        if not delegation.scope.actions.issubset(frozenset(grant_actions)):
            raise ContractError("la delegación amplía las acciones del Grant")
        grant_expires_at = _parse_timestamp(row["expires_at"], "grant.expires_at")
        if delegation.expires_at > grant_expires_at:
            raise ContractError("la delegación no puede exceder la expiración del Grant")

    @staticmethod
    def _values(delegation: AgentDelegation) -> tuple[object, ...]:
        if not isinstance(delegation, AgentDelegation):
            raise ContractError("delegation debe ser AgentDelegation")
        return (
            delegation.delegation_id,
            delegation.owner_user_id,
            delegation.owner_identity_id,
            delegation.agent_identity_id,
            delegation.grant_id,
            delegation.grant_revision,
            delegation.project_id,
            delegation.environment,
            delegation.scope.resource_type,
            json.dumps(sorted(delegation.scope.resource_ids), separators=(",", ":")),
            json.dumps(sorted(delegation.scope.actions), separators=(",", ":")),
            delegation.issuer_id,
            _timestamp(delegation.issued_at, "issued_at"),
            _timestamp(delegation.not_before, "not_before"),
            _timestamp(delegation.expires_at, "expires_at"),
            delegation.created_by_user_identity_id,
            delegation.status.value,
            delegation.revision,
            None if delegation.revoked_at is None else _timestamp(delegation.revoked_at, "revoked_at"),
            delegation.revoked_by_user_id,
        )

    def create(self, delegation: AgentDelegation) -> None:
        values = self._values(delegation)
        if delegation.status is not AgentDelegationStatus.ACTIVE or delegation.revision != 1:
            raise ContractError("una delegación nueva debe estar ACTIVE en revisión 1")
        try:
            with self._write_connection() as connection:
                self._validate_grant_subset(connection, delegation)
                connection.execute(
                    """
                    INSERT INTO agent_delegations (
                        delegation_id, owner_user_id, owner_identity_id,
                        agent_identity_id, grant_id, grant_revision, project_id,
                        environment, resource_type, resource_ids_json, actions_json,
                        issuer_id, issued_at, not_before, expires_at,
                        created_by_user_identity_id, status, revision, revoked_at,
                        revoked_by_user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("conflicto de integridad al crear delegación") from exc

    def get(self, delegation_id: str) -> AgentDelegation | None:
        validate_canonical_uuid4(delegation_id, "delegation_id")
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_delegations WHERE delegation_id = ?",
                (delegation_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, delegation: AgentDelegation) -> None:
        values = self._values(delegation)
        with self._write_connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_delegations WHERE delegation_id = ?",
                (delegation.delegation_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("delegación no encontrada")
            current = self._from_row(row)
            validate_agent_delegation_transition(current, delegation)
            if delegation == current:
                return
            cursor = connection.execute(
                """
                UPDATE agent_delegations
                SET status = ?, revision = ?, revoked_at = ?, revoked_by_user_id = ?
                WHERE delegation_id = ? AND revision = ?
                """,
                (
                    values[16], values[17], values[18], values[19],
                    delegation.delegation_id, current.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError("la delegación cambió durante la actualización")

    def revoke(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        revoked_at: datetime,
        revoked_by_user_id: str,
    ) -> AgentDelegation:
        validate_canonical_uuid4(delegation_id, "delegation_id")
        validate_canonical_uuid4(revoked_by_user_id, "revoked_by_user_id")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ContractError("expected_revision debe ser entero positivo")
        _timestamp(revoked_at, "revoked_at")
        with self._write_connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_delegations WHERE delegation_id = ?",
                (delegation_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("delegación no encontrada")
            current = self._from_row(row)
            if current.revision != expected_revision:
                raise ConcurrencyError("revisión de delegación obsoleta")
            if current.status is AgentDelegationStatus.REVOKED:
                return current
            updated = replace(
                current,
                status=AgentDelegationStatus.REVOKED,
                revision=current.revision + 1,
                revoked_at=revoked_at,
                revoked_by_user_id=revoked_by_user_id,
            )
            validate_agent_delegation_transition(current, updated)
            cursor = connection.execute(
                """
                UPDATE agent_delegations
                SET status = 'revoked', revision = ?, revoked_at = ?,
                    revoked_by_user_id = ?
                WHERE delegation_id = ? AND revision = ? AND status = 'active'
                """,
                (
                    updated.revision, _timestamp(revoked_at, "revoked_at"),
                    revoked_by_user_id, delegation_id, expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyError("la delegación cambió durante la revocación")
            return updated

    def list_by_grant(self, grant_id: str) -> tuple[AgentDelegation, ...]:
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ContractError("grant_id debe ser cadena no vacía")
        with self._read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_delegations WHERE grant_id = ? ORDER BY delegation_id",
                (grant_id,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)
